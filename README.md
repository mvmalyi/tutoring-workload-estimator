# Teaching Workload Planner

A Streamlit application for visualising teaching positions and their expected
monthly workload.

Access it via this link: https://mvmalyi-tutoring-workload-estimator.streamlit.app/

## Features

* Editable teaching-position table.
* Semester-specific date validation.
* Teaching-position Gantt chart.
* Monthly workload distribution.
* PNG, PDF, and SVG chart downloads.
* CSV data downloads.
* UK date formatting.

## Installation

Python 3.10 or later is recommended.

Create and activate a virtual environment:

    python -m venv .venv

On macOS or Linux:

    source .venv/bin/activate

On Windows PowerShell:

    .venv\Scripts\Activate.ps1

Install the dependencies:

    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt

## Running the application

From the project directory, run:

    streamlit run app.py

Streamlit should open the application automatically in your browser.

## Workload calculation

Expected hours are distributed uniformly across every calendar day between
the start and end dates. Both boundary dates are included, and weekdays and
weekends are treated equally.
