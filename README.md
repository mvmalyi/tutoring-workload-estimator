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

## Workload calculation

Expected hours are distributed uniformly across every calendar day between
the start and end dates. Both boundary dates are included, and weekdays and
weekends are treated equally.
