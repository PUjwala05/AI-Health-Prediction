# AI Health Prediction System

## About the Project

The **AI Health Prediction System** is a web-based application developed using Python and Flask. It allows users to enter patient details, store patient records in MongoDB, assign test numbers, and generate health-related remarks using the Google Gemini API.

## Features

- Patient registration and details management
- Automatic test number assignment
- MongoDB database integration
- AI-generated health-related remarks using Google Gemini
- Web interface built with HTML and CSS

## Technologies Used

- Python
- Flask
- MongoDB
- Google Gemini API
- HTML and CSS

## Prerequisites

Before running the project, install:

- Python 3.10 or a compatible version
- MongoDB
- A Google Gemini API key

## Installation and Setup

### 1. Clone the Repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd AI_Health_Prediction
```

Replace `YOUR_GITHUB_REPOSITORY_URL` with the actual repository URL.

### 2. Create a Virtual Environment

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root directory and add your own Gemini API key:

```env
GEMINI_API_KEY=your_own_gemini_api_key
```

Obtain an API key from [Google AI Studio](https://aistudio.google.com/).

**Security note:** Never share your API key or upload your `.env` file to GitHub.

### 5. Configure MongoDB

Ensure MongoDB is installed and running. Update the database connection settings in the application if necessary.

### 6. Run the Application

```bash
python app.py
```

Open the local URL displayed in the terminal in your browser.

## Important Notes

- Each user must configure their own Gemini API key.
- The application requires a working MongoDB connection to store patient records.
- Gemini API availability and usage limits depend on the user's API account.
- AI-generated remarks are informational only and are not a substitute for professional medical advice.

## Author

**Perugu Ujwala**
