
from pymongo import MongoClient, ReturnDocument

client = MongoClient("mongodb://localhost:27017/")
db = client["ai_health_db"]
patients = db["patients"]
counters = db["counters"]

# Find the highest existing test number.
highest = 0

for patient in patients.find({}, {"test_number": 1}):
    number = patient.get("test_number", "")

    if isinstance(number, str) and number.startswith("TEST"):
        suffix = number[4:]
        if suffix.isdigit():
            highest = max(highest, int(suffix))

# Set the counter without resetting it to a lower value.
counters.update_one(
    {"_id": "patient_test_number"},
    {"$max": {"sequence": highest}},
    upsert=True,
)

# Assign permanent numbers to records missing them.
missing_records = patients.find({
    "$or": [
        {"test_number": {"$exists": False}},
        {"test_number": None},
        {"test_number": ""},
    ]
}).sort("_id", 1)

for patient in missing_records:
    counter = counters.find_one_and_update(
        {"_id": "patient_test_number"},
        {"$inc": {"sequence": 1}},
        return_document=ReturnDocument.AFTER,
    )

    test_number = f"TEST{counter['sequence']:03d}"

    result = patients.update_one(
        {
            "_id": patient["_id"],
            "$or": [
                {"test_number": {"$exists": False}},
                {"test_number": None},
                {"test_number": ""},
            ],
        },
        {"$set": {"test_number": test_number}},
    )

    if result.modified_count:
        print(patient.get("full_name"), "->", test_number)

print("Test-number repair finished.")
client.close()
