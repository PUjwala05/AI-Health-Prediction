import os
import re
import math
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import PyMongoError
from bson.objectid import ObjectId
from dotenv import load_dotenv
from google import genai
from google.genai import types


# ==================================================
# CONFIGURATION
# ==================================================

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "local-development-key-change-before-deployment",
)

logging.basicConfig(level=logging.INFO)


# ==================================================
# MONGODB CONNECTION
# ==================================================

client = MongoClient(
    "mongodb://localhost:27017/",
    serverSelectionTimeoutMS=5000,
)

db = client["ai_health_db"]
patients = db["patients"]
counters = db["counters"]

COUNTER_ID = "patient_test_number"


# ==================================================
# TEST NUMBER MANAGEMENT
# ==================================================

def generate_test_number():
    """
    Atomically generate the next permanent test number.
    Example: TEST001, TEST002, TEST003.
    """

    counter = counters.find_one_and_update(
        {"_id": COUNTER_ID},
        {"$inc": {"sequence": 1}},
        return_document=ReturnDocument.AFTER,
        upsert=True,
    )

    return f"TEST{counter['sequence']:03d}"


def initialize_test_numbers():
    """
    Run at application startup.
    Preserve assigned numbers and assign numbers to old records
    that are missing them.
    """

    highest_number = 0

    # Find the highest existing valid test number.
    for record in patients.find(
        {"test_number": {"$regex": r"^TEST\d+$"}},
        {"test_number": 1},
    ):
        match = re.fullmatch(
            r"TEST(\d+)",
            record.get("test_number", ""),
        )

        if match:
            highest_number = max(
                highest_number,
                int(match.group(1)),
            )

    # Never reduce the existing counter.
    counters.update_one(
        {"_id": COUNTER_ID},
        {"$max": {"sequence": highest_number}},
        upsert=True,
    )

    # Repair older records missing a number.
    missing_records = patients.find(
        {
            "$or": [
                {"test_number": {"$exists": False}},
                {"test_number": None},
                {"test_number": ""},
                {"test_number":"Not Assigned"}
            ]
        }
    ).sort("_id", 1)

    for record in missing_records:
        test_number = generate_test_number()

        result = patients.update_one(
            {
                "_id": record["_id"],
                "$or": [
                    {"test_number": {"$exists": False}},
                    {"test_number": None},
                    {"test_number": ""},
                ],
            },
            {"$set": {"test_number": test_number}},
        )

        if result.modified_count:
            app.logger.info(
                "Assigned %s to existing patient %s",
                test_number,
                record.get("full_name", "Unknown"),
            )

    # Enforce unique test numbers.
    patients.create_index(
        "test_number",
        unique=True,
        sparse=True,
    )

    app.logger.info("Test-number initialization completed.")


# ==================================================
# GEMINI API CONNECTION
# ==================================================

api_key = os.getenv("GEMINI_API_KEY")
gemini_client = None

if api_key:
    gemini_client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=60000),
    )
else:
    app.logger.warning(
        "GEMINI_API_KEY is missing from the .env file."
    )

executor = ThreadPoolExecutor(max_workers=2)


# ==================================================
# VALIDATION
# ==================================================

def validate_patient(data):
    full_name = data.get("full_name", "").strip()
    dob_text = data.get("date_of_birth", "").strip()
    email = data.get("email", "").strip()

    if not full_name:
        return "Full name is required."

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return "Please enter a valid email address."

    try:
        dob = datetime.strptime(dob_text, "%d/%m/%Y")

        if dob.strftime("%d/%m/%Y") != dob_text:
            return "Enter date of birth in DD/MM/YYYY format."

        if dob.date() > datetime.today().date():
            return "Date of birth cannot be in the future."

    except ValueError:
        return "Enter a valid date in DD/MM/YYYY format."

    for field in ("glucose", "haemoglobin", "cholesterol"):
        try:
            value = float(data.get(field, ""))

            if not math.isfinite(value) or value <= 0:
                return f"{field.title()} must be a positive number."

        except (ValueError, TypeError):
            return f"{field.title()} must be numeric."

    return None


# ==================================================
# GENERATE AI HEALTH REMARK
# ==================================================

def generate_ai_remarks(glucose, haemoglobin, cholesterol):
    if gemini_client is None:
        raise RuntimeError(
            "Gemini client is not configured. Check GEMINI_API_KEY."
        )

    prompt = f"""
You are generating an educational remark for a health-record
demonstration application.

Recorded laboratory values:
Glucose: {glucose}
Haemoglobin: {haemoglobin}
Total cholesterol: {cholesterol}

Write 2 to 4 concise sentences.

Explain that interpretation depends on units, laboratory reference
ranges, fasting status, age, and clinical context.

Do not diagnose a disease or invent units, medical history,
or risk percentages.

Recommend consulting a qualified healthcare professional.
State that this is informational and not a diagnosis.

Return only the remark.
"""

    response = gemini_client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
    )

    remark = (response.text or "").strip()

    if not remark:
        raise RuntimeError("Gemini returned an empty response.")

    return remark


# ==================================================
# BACKGROUND AI TASK
# ==================================================

def generate_and_save_remark(
    patient_id,
    glucose,
    haemoglobin,
    cholesterol,
):
    try:
        remark = generate_ai_remarks(
            glucose,
            haemoglobin,
            cholesterol,
        )

        patients.update_one(
            {"_id": patient_id},
            {"$set": {"remarks": remark}},
        )

        app.logger.info(
            "AI remark saved for patient %s",
            patient_id,
        )

    except Exception as error:
        app.logger.exception(
            "Gemini generation failed for patient %s",
            patient_id,
        )

        try:
            patients.update_one(
                {"_id": patient_id},
                {
                    "$set": {
                        "remarks": (
                            f"AI request failed: "
                            f"{type(error).__name__}: {error}"
                        )
                    }
                },
            )
        except Exception:
            app.logger.exception(
                "Could not save AI failure status."
            )


def queue_ai_remark(
    patient_id,
    glucose,
    haemoglobin,
    cholesterol,
):
    executor.submit(
        generate_and_save_remark,
        patient_id,
        glucose,
        haemoglobin,
        cholesterol,
    )


# ==================================================
# HOME PAGE: CREATE AND READ PATIENTS
# ==================================================

@app.route("/", methods=["GET", "POST"])
def home():

    if request.method == "POST":
        error = validate_patient(request.form)

        if error:
            flash(error, "error")
            return redirect(url_for("home"))

        try:
            # Generate a number automatically for every new patient.
            test_number = generate_test_number()
            if not test_number:
                raise ValueError("Test number generation failed")

            patient = {
                "test_number": test_number,
                "full_name": request.form["full_name"].strip(),
                "date_of_birth": request.form["date_of_birth"].strip(),
                "email": request.form["email"].strip(),
                "glucose": float(request.form["glucose"]),
                "haemoglobin": float(request.form["haemoglobin"]),
                "cholesterol": float(request.form["cholesterol"]),
                "remarks": "Generating AI remark...",
            }

            # Save the test number with the patient record.
            result = patients.insert_one(patient)

            app.logger.info(
                "Saved patient %s with test number %s",
                patient["full_name"],
                test_number,
            )

            queue_ai_remark(
                result.inserted_id,
                patient["glucose"],
                patient["haemoglobin"],
                patient["cholesterol"],
            )

            flash(
                f"Patient saved successfully! Test No: {test_number}",
                "success",
            )

        except Exception:
            app.logger.exception("Could not save patient.")

            flash(
                "Could not save patient. Check MongoDB and terminal logs.",
                "error",
            )

        return redirect(url_for("home"))

    # GET: repair missing numbers before displaying records.
    try:
        initialize_test_numbers()

        all_patients = list(
            patients.find().sort("_id", -1)
        )

    except Exception:
        app.logger.exception(
            "Could not load patient records or initialize test numbers."
        )

        all_patients = []

        flash(
            "Could not load records. Check MongoDB and terminal logs.",
            "error",
        )

    return render_template(
        "index.html",
        patients=all_patients,
    )


# ==================================================
# FETCH LATEST AI REMARK
# ==================================================

@app.route("/remarks/<patient_id>", methods=["GET"])
def get_remark(patient_id):

    if not ObjectId.is_valid(patient_id):
        return jsonify({"error": "Invalid patient ID"}), 400

    try:
        patient = patients.find_one(
            {"_id": ObjectId(patient_id)},
            {"remarks": 1},
        )

    except Exception:
        app.logger.exception("Could not fetch AI remark.")
        return jsonify({"error": "Database error"}), 500

    if patient is None:
        return jsonify({"error": "Patient not found"}), 404

    return jsonify({
        "remarks": patient.get(
            "remarks",
            "No remark available.",
        )
    })


# ==================================================
# UPDATE PATIENT
# ==================================================

@app.route("/edit/<patient_id>", methods=["GET", "POST"])
def edit_patient(patient_id):

    if not ObjectId.is_valid(patient_id):
        flash("Invalid patient ID.", "error")
        return redirect(url_for("home"))

    object_id = ObjectId(patient_id)
    patient = patients.find_one({"_id": object_id})

    if patient is None:
        flash("Patient record not found.", "error")
        return redirect(url_for("home"))

    if request.method == "POST":
        error = validate_patient(request.form)

        if error:
            flash(error, "error")
            return redirect(
                url_for("edit_patient", patient_id=patient_id)
            )

        updated_data = {
            "full_name": request.form["full_name"].strip(),
            "date_of_birth": request.form["date_of_birth"].strip(),
            "email": request.form["email"].strip(),
            "glucose": float(request.form["glucose"]),
            "haemoglobin": float(request.form["haemoglobin"]),
            "cholesterol": float(request.form["cholesterol"]),
            "remarks": "Generating AI remark...",
        }

        try:
            # Keep the existing test number when editing.
            patients.update_one(
                {"_id": object_id},
                {"$set": updated_data},
            )

            queue_ai_remark(
                object_id,
                updated_data["glucose"],
                updated_data["haemoglobin"],
                updated_data["cholesterol"],
            )

            flash(
                f"Patient {patient.get('test_number', '')} updated.",
                "success",
            )

        except Exception:
            app.logger.exception("Could not update patient.")
            flash("Could not update patient.", "error")

        return redirect(url_for("home"))

    return render_template(
        "edit.html",
        patient=patient,
    )


# ==================================================
# DELETE PATIENT
# ==================================================

@app.route("/delete/<patient_id>", methods=["POST"])
def delete_patient(patient_id):

    if not ObjectId.is_valid(patient_id):
        flash("Invalid patient ID.", "error")
        return redirect(url_for("home"))

    try:
        result = patients.delete_one(
            {"_id": ObjectId(patient_id)}
        )

        if result.deleted_count:
            flash("Patient deleted successfully!", "success")
        else:
            flash("Patient record not found.", "error")

    except Exception:
        app.logger.exception("Could not delete patient.")
        flash("Could not delete patient.", "error")

    # Do not decrement the counter or reuse a deleted number.
    return redirect(url_for("home"))


# ==================================================
# START FLASK
# ==================================================

if __name__ == "__main__":

    try:
        client.admin.command("ping")
        print("MongoDB connected successfully.")

        # Initialize old records and counter once at startup.
        initialize_test_numbers()

    except Exception:
        app.logger.exception(
            "MongoDB connection or test-number initialization failed."
        )
        raise

    if gemini_client is None:
        print("WARNING: GEMINI_API_KEY is missing from .env")

    app.run(
        debug=True,
        use_reloader=False,
    )