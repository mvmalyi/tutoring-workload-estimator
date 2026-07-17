"""Interactive Streamlit app for visualising teaching workload.

The app creates:

1. A Gantt chart showing the duration of each teaching position.
2. A monthly bar chart showing the expected workload.
3. Downloadable chart and data files.

Expected hours are distributed uniformly across every calendar day between
the start and end dates, including both boundary dates.
"""

from __future__ import annotations

import math
import re
from datetime import date
from io import BytesIO
from typing import TypeAlias

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from matplotlib.colors import (
    LinearSegmentedColormap,
    Normalize,
    to_rgb,
)


RGBColour: TypeAlias = tuple[float, float, float]
RGBAColour: TypeAlias = tuple[float, float, float, float]
PositionKey: TypeAlias = tuple[str, str]

TASK_COLUMNS = [
    "course",
    "position",
    "hours",
    "start",
    "end",
]

DEFAULT_YEAR = 2026
DEFAULT_SEMESTER = 1
DEFAULT_TITLE = "Course Timelines and Monthly Workload Distribution"
DEFAULT_WORKLOAD_COLOUR = "#7d3c98"
DEFAULT_FIGURE_WIDTH = 12.0
DEFAULT_FIGURE_HEIGHT = 10.0
DEFAULT_DISPLAY_DPI = 900
DEFAULT_OUTPUT_DPI = 300


# =============================================================================
# STREAMLIT CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="Teaching Workload Planner",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed",
)



# =============================================================================
# DATA PREPARATION
# =============================================================================


def get_semester_bounds(
    year: int,
    semester: int,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return the inclusive start and end dates for a semester.

    Args:
        year: Calendar year associated with the semester.
        semester: Semester number, either 1 or 2.

    Returns:
        The inclusive semester start and end dates.

    Raises:
        ValueError: If semester is not 1 or 2.
    """
    if semester == 1:
        start = pd.Timestamp(year=year, month=9, day=1)
        end = pd.Timestamp(year=year + 1, month=1, day=31)
    elif semester == 2:
        start = pd.Timestamp(year=year, month=1, day=1)
        end = pd.Timestamp(year=year, month=5, day=31)
    else:
        raise ValueError(
            f"Semester must be 1 or 2, but {semester!r} was supplied."
        )

    return start, end


def create_example_tasks(
    year: int,
    semester: int,
) -> pd.DataFrame:
    """Create example teaching positions for the selected semester.

    Args:
        year: Calendar year associated with the semester.
        semester: Semester number, either 1 or 2.

    Returns:
        Example task data suitable for the Streamlit data editor.
    """
    if semester == 1:
        records = [
            {
                "course": "Course One",
                "position": "Demonstrator",
                "hours": 12.0,
                "start": f"{year}-09-28",
                "end": f"{year}-10-23",
            },
            {
                "course": "Course One",
                "position": "Tutor",
                "hours": 24.0,
                "start": f"{year}-10-26",
                "end": f"{year}-11-20",
            },
            {
                "course": "Course Two",
                "position": "Tutor",
                "hours": 7.0,
                "start": f"{year}-11-16",
                "end": f"{year}-11-27",
            },
            {
                "course": "Course Two",
                "position": "Marker",
                "hours": 24.0,
                "start": f"{year}-11-30",
                "end": f"{year + 1}-01-08",
            },
            {
                "course": "Course Three",
                "position": "Demonstrator",
                "hours": 30.0,
                "start": f"{year}-09-28",
                "end": f"{year}-12-04",
            },
        ]
    else:
        records = [
            {
                "course": "Course One",
                "position": "Demonstrator",
                "hours": 12.0,
                "start": f"{year}-01-12",
                "end": f"{year}-02-06",
            },
            {
                "course": "Course One",
                "position": "Tutor",
                "hours": 24.0,
                "start": f"{year}-02-09",
                "end": f"{year}-03-06",
            },
            {
                "course": "Course Two",
                "position": "Tutor",
                "hours": 7.0,
                "start": f"{year}-03-02",
                "end": f"{year}-03-13",
            },
            {
                "course": "Course Two",
                "position": "Marker",
                "hours": 24.0,
                "start": f"{year}-03-16",
                "end": f"{year}-04-24",
            },
            {
                "course": "Course Three",
                "position": "Demonstrator",
                "hours": 30.0,
                "start": f"{year}-01-12",
                "end": f"{year}-05-01",
            },
        ]

    data = pd.DataFrame(records, columns=TASK_COLUMNS)
    data["start"] = pd.to_datetime(data["start"])
    data["end"] = pd.to_datetime(data["end"])

    return data


def create_empty_task_data() -> pd.DataFrame:
    """Return an empty DataFrame with the required task columns."""
    return pd.DataFrame(
        {
            "course": pd.Series(dtype="object"),
            "position": pd.Series(dtype="object"),
            "hours": pd.Series(dtype="float64"),
            "start": pd.Series(dtype="datetime64[ns]"),
            "end": pd.Series(dtype="datetime64[ns]"),
        }
    )


def prepare_task_data(
    task_records: pd.DataFrame,
    semester_start: pd.Timestamp,
    semester_end: pd.Timestamp,
) -> pd.DataFrame:
    """Convert user input into a validated task DataFrame.

    Args:
        task_records: User-supplied teaching position records.
        semester_start: Inclusive first date of the semester.
        semester_end: Inclusive final date of the semester.

    Returns:
        Validated task data sorted chronologically.

    Raises:
        ValueError: If records are missing, invalid, or outside the semester.
    """
    if task_records is None or task_records.empty:
        raise ValueError(
            "Add at least one teaching position before creating the chart."
        )

    missing_columns = set(TASK_COLUMNS).difference(task_records.columns)

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            "The following required fields are missing: "
            f"{missing_text}."
        )

    data = task_records.loc[:, TASK_COLUMNS].copy()

    data = data.replace(r"^\s*$", pd.NA, regex=True)
    data = data.dropna(how="all").reset_index(drop=True)

    if data.empty:
        raise ValueError(
            "Add at least one teaching position before creating the chart."
        )

    incomplete_rows = data[TASK_COLUMNS].isna().any(axis=1)

    if incomplete_rows.any():
        row_numbers = [
            str(index + 1)
            for index in data.index[incomplete_rows]
        ]
        rows_text = ", ".join(row_numbers)

        raise ValueError(
            "Every field is required. Complete all fields in table "
            f"row(s): {rows_text}."
        )

    data["course"] = data["course"].astype(str).str.strip()
    data["position"] = data["position"].astype(str).str.strip()

    if data["course"].eq("").any():
        invalid_rows = data.index[data["course"].eq("")] + 1
        rows_text = ", ".join(map(str, invalid_rows))

        raise ValueError(
            f"Enter a course name in table row(s): {rows_text}."
        )

    if data["position"].eq("").any():
        invalid_rows = data.index[data["position"].eq("")] + 1
        rows_text = ", ".join(map(str, invalid_rows))

        raise ValueError(
            f"Enter a position name in table row(s): {rows_text}."
        )

    data["hours"] = pd.to_numeric(
        data["hours"],
        errors="coerce",
    )

    invalid_hours = (
        data["hours"].isna()
        | data["hours"].le(0)
        | ~data["hours"].map(
            lambda value: math.isfinite(float(value))
            if pd.notna(value)
            else False
        )
    )

    if invalid_hours.any():
        invalid_rows = data.index[invalid_hours] + 1
        rows_text = ", ".join(map(str, invalid_rows))

        raise ValueError(
            "Hours must be positive, finite numbers in table "
            f"row(s): {rows_text}."
        )

    data["start"] = pd.to_datetime(
        data["start"],
        errors="coerce",
        dayfirst=True,
    ).dt.normalize()

    data["end"] = pd.to_datetime(
        data["end"],
        errors="coerce",
        dayfirst=True,
    ).dt.normalize()

    invalid_dates = data[["start", "end"]].isna().any(axis=1)

    if invalid_dates.any():
        invalid_rows = data.index[invalid_dates] + 1
        rows_text = ", ".join(map(str, invalid_rows))

        raise ValueError(
            "Enter valid start and end dates in table "
            f"row(s): {rows_text}."
        )

    invalid_date_order = data["end"] < data["start"]

    if invalid_date_order.any():
        invalid_rows = data.index[invalid_date_order] + 1
        rows_text = ", ".join(map(str, invalid_rows))

        raise ValueError(
            "The end date occurs before the start date in table "
            f"row(s): {rows_text}."
        )

    outside_semester = (
        data["start"].lt(semester_start)
        | data["end"].gt(semester_end)
    )

    if outside_semester.any():
        invalid_tasks = data.loc[
            outside_semester,
            ["course", "position", "start", "end"],
        ]

        task_descriptions = [
            (
                f"Row {row.Index + 1}, {row.course}: {row.position}, "
                f"{row.start:%d/%m/%Y} to {row.end:%d/%m/%Y}"
            )
            for row in invalid_tasks.itertuples()
        ]

        descriptions = "\n".join(
            f"* {description}"
            for description in task_descriptions
        )

        raise ValueError(
            "The following positions fall outside the selected semester:\n\n"
            f"{descriptions}\n\n"
            f"Selected semester: {semester_start:%d/%m/%Y} to "
            f"{semester_end:%d/%m/%Y}."
        )

    data["duration_days"] = (
        data["end"] - data["start"]
    ).dt.days + 1

    data["hours_per_day"] = (
        data["hours"] / data["duration_days"]
    )

    data["label"] = data.apply(
        lambda row: (
            f"{row['course']}: {row['position']} "
            f"({row['hours']:g} hours)"
        ),
        axis=1,
    )

    return data.sort_values(
        by=["start", "end", "course", "position"],
        ascending=True,
    ).reset_index(drop=True)


def calculate_monthly_workload(
    tasks: pd.DataFrame,
    semester_start: pd.Timestamp,
    semester_end: pd.Timestamp,
) -> pd.Series:
    """Calculate workload totals for every month in the semester.

    Hours are distributed uniformly across all calendar days covered by each
    position. Weekends and weekdays are treated equally.

    Args:
        tasks: Validated teaching position data.
        semester_start: Inclusive semester start date.
        semester_end: Inclusive semester end date.

    Returns:
        Monthly workload totals indexed by the first day of each month.
    """
    semester_dates = pd.date_range(
        start=semester_start,
        end=semester_end,
        freq="D",
    )

    daily_hours = pd.Series(
        data=0.0,
        index=semester_dates,
        dtype=float,
    )

    for task in tasks.itertuples():
        task_dates = pd.date_range(
            start=task.start,
            end=task.end,
            freq="D",
        )

        daily_hours.loc[task_dates] += task.hours_per_day

    monthly_hours = daily_hours.resample("MS").sum()

    month_starts = pd.date_range(
        start=semester_start,
        end=semester_end,
        freq="MS",
    )

    return monthly_hours.reindex(
        month_starts,
        fill_value=0.0,
    )


# =============================================================================
# COLOUR GENERATION
# =============================================================================


def blend_with_white(
    colour: str | RGBColour,
    white_fraction: float,
) -> RGBColour:
    """Blend a colour with white to create a lighter tint.

    Args:
        colour: Matplotlib-compatible colour or RGB tuple.
        white_fraction: Proportion of white, between 0 and 1.

    Returns:
        The resulting RGB colour.

    Raises:
        ValueError: If white_fraction is outside the interval from 0 to 1.
    """
    if not 0.0 <= white_fraction <= 1.0:
        raise ValueError(
            "white_fraction must be between 0 and 1."
        )

    red, green, blue = to_rgb(colour)

    return (
        red + (1.0 - red) * white_fraction,
        green + (1.0 - green) * white_fraction,
        blue + (1.0 - blue) * white_fraction,
    )


def create_position_colours(
    tasks: pd.DataFrame,
) -> dict[PositionKey, RGBColour]:
    """Assign related colours to positions within the same course.

    Args:
        tasks: Validated teaching position data.

    Returns:
        Mapping from course-position pairs to RGB colours.
    """
    course_names = list(dict.fromkeys(tasks["course"]))
    palette = plt.get_cmap("tab10").colors

    colours: dict[PositionKey, RGBColour] = {}

    for course_number, course_name in enumerate(course_names):
        base_colour = palette[course_number % len(palette)]

        course_positions = tasks.loc[
            tasks["course"].eq(course_name),
            "position",
        ]

        position_names = list(dict.fromkeys(course_positions))

        if len(position_names) == 1:
            tint_values = [0.15]
        else:
            tint_step = 0.30 / (len(position_names) - 1)
            tint_values = [
                0.05 + position_number * tint_step
                for position_number in range(len(position_names))
            ]

        for position_name, tint in zip(
            position_names,
            tint_values,
            strict=True,
        ):
            key = (course_name, position_name)
            colours[key] = blend_with_white(
                base_colour,
                tint,
            )

    return colours


def create_workload_colours(
    monthly_hours: pd.Series,
    base_colour: str,
) -> list[RGBAColour]:
    """Create a light-to-dark workload colour gradient.

    Args:
        monthly_hours: Monthly workload totals.
        base_colour: Base Matplotlib-compatible colour.

    Returns:
        One RGBA colour for each monthly value.
    """
    light_colour = blend_with_white(
        base_colour,
        0.75,
    )

    colour_map = LinearSegmentedColormap.from_list(
        "monthly_workload",
        [light_colour, to_rgb(base_colour)],
    )

    maximum_hours = float(monthly_hours.max())

    normaliser = Normalize(
        vmin=0.0,
        vmax=max(maximum_hours, 1.0),
    )

    return [
        colour_map(normaliser(float(hours)))
        for hours in monthly_hours
    ]


# =============================================================================
# PLOTTING
# =============================================================================


def add_time_grid(
    axis: plt.Axes,
    month_starts: pd.DatetimeIndex,
    semester_end_exclusive: pd.Timestamp,
    include_weeks: bool,
) -> None:
    """Add month boundaries and optional weekly grid lines.

    Args:
        axis: Matplotlib axis receiving the grid.
        month_starts: First day of every displayed month.
        semester_end_exclusive: First day after the semester.
        include_weeks: Whether to include weekly grid lines.
    """
    month_boundaries = month_starts.append(
        pd.DatetimeIndex([semester_end_exclusive])
    )

    if include_weeks:
        weekly_dates = pd.date_range(
            start=month_starts[0],
            end=semester_end_exclusive,
            freq="W-MON",
        )

        for weekly_date in weekly_dates:
            axis.axvline(
                weekly_date,
                color="#b0b0b0",
                linestyle="--",
                linewidth=0.7,
                alpha=0.35,
                zorder=0,
            )

    for boundary_date in month_boundaries:
        axis.axvline(
            boundary_date,
            color="#333333",
            linestyle="-",
            linewidth=1.0,
            alpha=0.65,
            zorder=1,
        )


def plot_workload(
    tasks: pd.DataFrame,
    monthly_hours: pd.Series,
    semester_start: pd.Timestamp,
    semester_end: pd.Timestamp,
    semester: int,
    title: str,
    workload_base_colour: str,
    figure_size: tuple[float, float],
) -> plt.Figure:
    """Create the Gantt chart and monthly workload chart.

    Args:
        tasks: Validated teaching position data.
        monthly_hours: Monthly expected workload totals.
        semester_start: Inclusive semester start date.
        semester_end: Inclusive semester end date.
        semester: Semester number.
        title: Main figure title.
        workload_base_colour: Base colour for monthly bars.
        figure_size: Matplotlib figure width and height in inches.

    Returns:
        Completed Matplotlib figure.
    """
    semester_end_exclusive = semester_end + pd.Timedelta(days=1)
    month_starts = monthly_hours.index
    next_month_starts = month_starts + pd.offsets.MonthBegin(1)

    month_widths = (
        next_month_starts - month_starts
    ).days.to_numpy()

    month_centres = month_starts + pd.to_timedelta(
        month_widths / 2,
        unit="D",
    )

    position_colours = create_position_colours(tasks)

    workload_colours = create_workload_colours(
        monthly_hours,
        workload_base_colour,
    )

    figure, (gantt_axis, workload_axis) = plt.subplots(
        nrows=2,
        ncols=1,
        figsize=figure_size,
        sharex=True,
        gridspec_kw={"height_ratios": [2.2, 1.0]},
        constrained_layout=True,
    )

    figure.suptitle(
        title,
        fontsize=16,
        fontweight="bold",
    )

    y_positions = list(range(len(tasks)))

    for y_position, task in zip(
        y_positions,
        tasks.itertuples(),
        strict=True,
    ):
        colour_key = (task.course, task.position)

        gantt_axis.barh(
            y=y_position,
            width=task.duration_days,
            left=task.start,
            height=0.78,
            color=position_colours[colour_key],
            edgecolor="#202020",
            linewidth=1.0,
            alpha=0.95,
            zorder=2,
        )

    gantt_axis.set_yticks(y_positions)
    gantt_axis.set_yticklabels(tasks["label"])
    gantt_axis.invert_yaxis()
    gantt_axis.set_ylabel(
        "Teaching position",
        fontsize=11,
    )

    gantt_axis.tick_params(
        axis="x",
        which="both",
        bottom=False,
        labelbottom=False,
    )

    gantt_axis.grid(
        axis="y",
        color="#d0d0d0",
        linestyle=":",
        linewidth=0.7,
        alpha=0.5,
    )

    add_time_grid(
        axis=gantt_axis,
        month_starts=month_starts,
        semester_end_exclusive=semester_end_exclusive,
        include_weeks=True,
    )

    workload_axis.bar(
        x=month_starts,
        height=monthly_hours.to_numpy(),
        width=month_widths,
        align="edge",
        color=workload_colours,
        edgecolor="#202020",
        linewidth=1.0,
        alpha=0.95,
        zorder=2,
    )

    maximum_hours = float(monthly_hours.max())
    label_offset = max(maximum_hours * 0.025, 0.25)

    for month_centre, hours, days_in_month in zip(
        month_centres,
        monthly_hours,
        month_widths,
        strict=True,
    ):
        average_weekly_hours = (
            float(hours) * 7 / days_in_month
        )

        workload_axis.text(
            x=month_centre,
            y=float(hours) + label_offset,
            s=(
                f"{hours:.1f} h\n"
                f"({average_weekly_hours:.1f} h/week)"
            ),
            horizontalalignment="center",
            verticalalignment="bottom",
            fontsize=10,
            fontweight="bold",
            linespacing=1.25,
            clip_on=False,
        )

    workload_axis.set_ylabel(
        "Expected workload (hours)",
        fontsize=11,
    )

    workload_axis.set_xlabel(
        f"Semester {semester}: "
        f"{semester_start:%d %B %Y} to "
        f"{semester_end:%d %B %Y}",
        fontsize=10,
        labelpad=12,
    )

    workload_axis.set_xticks(month_centres)

    workload_axis.set_xticklabels(
        [
            month_start.strftime("%B %Y")
            for month_start in month_starts
        ],
        rotation=0,
        horizontalalignment="center",
    )

    workload_axis.tick_params(
        axis="x",
        which="both",
        length=0,
        pad=10,
    )

    workload_axis.grid(
        axis="y",
        color="#909090",
        linestyle="--",
        linewidth=0.8,
        alpha=0.45,
        zorder=0,
    )

    add_time_grid(
        axis=workload_axis,
        month_starts=month_starts,
        semester_end_exclusive=semester_end_exclusive,
        include_weeks=False,
    )

    workload_axis.set_ylim(
        bottom=0.0,
        top=max(maximum_hours * 1.25, 1.0),
    )

    workload_axis.set_xlim(
        semester_start,
        semester_end_exclusive,
    )

    gantt_axis.xaxis_date()
    workload_axis.xaxis_date()

    gantt_axis.margins(x=0)
    workload_axis.margins(x=0)

    return figure


# =============================================================================
# EXPORT FUNCTIONS
# =============================================================================


def figure_to_bytes(
    figure: plt.Figure,
    file_format: str,
    dpi: int,
) -> bytes:
    """Serialise a Matplotlib figure in memory.

    Args:
        figure: Figure to serialise.
        file_format: PNG, PDF, or SVG.
        dpi: Output resolution for raster formats.

    Returns:
        Serialised figure content.

    Raises:
        ValueError: If the output format is unsupported.
    """
    normalised_format = file_format.lower()

    if normalised_format not in {"png", "pdf", "svg"}:
        raise ValueError(
            f"Unsupported chart format: {file_format!r}."
        )

    output_buffer = BytesIO()

    figure.savefig(
        output_buffer,
        format=normalised_format,
        dpi=dpi,
        bbox_inches="tight",
    )

    output_buffer.seek(0)

    return output_buffer.getvalue()


def create_safe_filename(
    filename: str,
    extension: str,
) -> str:
    """Create a safe download filename.

    Args:
        filename: User-provided filename or stem.
        extension: Required file extension without a leading dot.

    Returns:
        Sanitised filename with the requested extension.
    """
    filename = filename.strip()

    if not filename:
        filename = "teaching_workload"

    filename = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        filename,
    )

    filename = filename.strip("._")

    if not filename:
        filename = "teaching_workload"

    current_extension = f".{extension.lower()}"

    if filename.lower().endswith(current_extension):
        return filename

    filename_stem = filename.rsplit(".", maxsplit=1)[0]

    return f"{filename_stem}.{extension.lower()}"


def tasks_to_csv(tasks: pd.DataFrame) -> bytes:
    """Convert validated tasks to a downloadable CSV file.

    Args:
        tasks: Validated task data.

    Returns:
        UTF-8 encoded CSV content.
    """
    export_data = tasks.loc[
        :,
        [
            "course",
            "position",
            "hours",
            "start",
            "end",
            "duration_days",
            "hours_per_day",
        ],
    ].copy()

    export_data["start"] = export_data["start"].dt.strftime(
        "%d/%m/%Y"
    )
    export_data["end"] = export_data["end"].dt.strftime(
        "%d/%m/%Y"
    )

    return export_data.to_csv(
        index=False,
        float_format="%.6f",
    ).encode("utf-8")


def monthly_workload_to_csv(
    monthly_hours: pd.Series,
) -> bytes:
    """Convert monthly workload totals to CSV format.

    Args:
        monthly_hours: Monthly workload totals.

    Returns:
        UTF-8 encoded CSV content.
    """
    export_data = monthly_hours.rename(
        "expected_hours"
    ).to_frame()

    export_data.index.name = "month"
    export_data = export_data.reset_index()

    export_data["month"] = export_data["month"].dt.strftime(
        "%B %Y"
    )

    days_in_month = monthly_hours.index.days_in_month

    export_data["average_weekly_hours"] = (
        export_data["expected_hours"] * 7 / days_in_month
    )

    return export_data.to_csv(
        index=False,
        float_format="%.3f",
    ).encode("utf-8")


def get_chart_mime_type(file_format: str) -> str:
    """Return the MIME type associated with a chart format."""
    mime_types = {
        "PNG": "image/png",
        "PDF": "application/pdf",
        "SVG": "image/svg+xml",
    }

    return mime_types[file_format.upper()]


# =============================================================================
# USER INTERFACE
# =============================================================================


def initialise_session_state(
    year: int,
    semester: int,
) -> None:
    """Initialise task editor state when the app first starts.

    Args:
        year: Initially selected year.
        semester: Initially selected semester.
    """
    if "task_data" not in st.session_state:
        st.session_state.task_data = create_example_tasks(
            year,
            semester,
        )

    if "editor_revision" not in st.session_state:
        st.session_state.editor_revision = 0


def render_semester_settings() -> dict[str, object]:
    """Render the semester controls at the top of the page.

    Returns:
        Selected year, semester, and corresponding semester bounds.
    """
    settings_column, spacer_column = st.columns([2, 3])

    with settings_column:
        year_column, semester_column = st.columns(2)

        with year_column:
            year = int(
                st.number_input(
                    "Year",
                    min_value=2000,
                    max_value=2100,
                    value=DEFAULT_YEAR,
                    step=1,
                    help=(
                        "For Semester 1, select the year in which "
                        "September occurs. For Semester 2, select the "
                        "calendar year containing the semester."
                    ),
                )
            )

        with semester_column:
            semester = int(
                st.selectbox(
                    "Semester",
                    options=[1, 2],
                    index=DEFAULT_SEMESTER - 1,
                )
            )

    semester_start, semester_end = get_semester_bounds(
        year=year,
        semester=semester,
    )

    return {
        "year": year,
        "semester": semester,
        "semester_start": semester_start,
        "semester_end": semester_end,
    }



def render_task_editor(
    year: int,
    semester: int,
    semester_start: pd.Timestamp,
    semester_end: pd.Timestamp,
) -> pd.DataFrame:
    """Render controls and the editable teaching-position table.

    Args:
        year: Selected semester year.
        semester: Selected semester number.
        semester_start: Inclusive semester start date.
        semester_end: Inclusive semester end date.

    Returns:
        Current contents of the task editor.
    """
    st.subheader("Teaching positions")

    st.write(
        "Add, edit, or delete rows in the table. Dates must fall "
        "within the selected semester."
    )

    button_column_1, button_column_2, information_column = st.columns(
        [1, 1, 3]
    )

    with button_column_1:
        if st.button(
            "Load example data",
            use_container_width=True,
        ):
            st.session_state.task_data = create_example_tasks(
                year,
                semester,
            )
            st.session_state.editor_revision += 1
            st.rerun()

    with button_column_2:
        if st.button(
            "Clear all rows",
            use_container_width=True,
        ):
            st.session_state.task_data = create_empty_task_data()
            st.session_state.editor_revision += 1
            st.rerun()

    with information_column:
        st.caption(
            "Use the plus button below the table to add positions. "
            "Select one or more rows to delete them."
        )

    editor_key = (
        f"task_editor_{st.session_state.editor_revision}"
    )

    edited_data = st.data_editor(
        st.session_state.task_data,
        key=editor_key,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_order=TASK_COLUMNS,
        column_config={
            "course": st.column_config.TextColumn(
                "Course",
                help="Course or module name.",
                required=True,
                width="medium",
            ),
            "position": st.column_config.TextColumn(
                "Position",
                help="For example, Tutor, Marker, or Demonstrator.",
                required=True,
                width="medium",
            ),
            "hours": st.column_config.NumberColumn(
                "Expected hours",
                help="Total expected hours for this position.",
                min_value=0.01,
                step=0.5,
                format="%.2f",
                required=True,
                width="small",
            ),
            "start": st.column_config.DateColumn(
                "Start date",
                help="Inclusive start date.",
                format="DD/MM/YYYY",
                min_value=semester_start.date(),
                max_value=semester_end.date(),
                required=True,
                width="small",
            ),
            "end": st.column_config.DateColumn(
                "End date",
                help="Inclusive end date.",
                format="DD/MM/YYYY",
                min_value=semester_start.date(),
                max_value=semester_end.date(),
                required=True,
                width="small",
            ),
        },
    )

    st.session_state.task_data = edited_data.copy()

    return edited_data


def render_summary_metrics(
    tasks: pd.DataFrame,
    monthly_hours: pd.Series,
) -> None:
    """Display high-level workload summary metrics.

    Args:
        tasks: Validated teaching position data.
        monthly_hours: Calculated monthly workload totals.
    """
    total_hours = float(tasks["hours"].sum())
    number_of_positions = len(tasks)
    number_of_courses = tasks["course"].nunique()

    peak_month_timestamp = monthly_hours.idxmax()
    peak_month_hours = float(monthly_hours.max())

    metric_columns = st.columns(4)

    metric_columns[0].metric(
        "Total expected hours",
        f"{total_hours:,.1f} h",
    )

    metric_columns[1].metric(
        "Teaching positions",
        f"{number_of_positions:,}",
    )

    metric_columns[2].metric(
        "Courses",
        f"{number_of_courses:,}",
    )

    metric_columns[3].metric(
        "Peak month",
        peak_month_timestamp.strftime("%B %Y"),
        delta=f"{peak_month_hours:,.1f} h",
        delta_color="off",
    )


def render_monthly_table(
    monthly_hours: pd.Series,
) -> None:
    """Display monthly workload results as a table.

    Args:
        monthly_hours: Calculated monthly workload totals.
    """
    results = monthly_hours.rename(
        "Expected hours"
    ).to_frame()

    results["Average weekly hours"] = (
        results["Expected hours"]
        * 7
        / results.index.days_in_month
    )

    results.index = results.index.strftime("%B %Y")
    results.index.name = "Month"

    st.dataframe(
        results.style.format(
            {
                "Expected hours": "{:.2f}",
                "Average weekly hours": "{:.2f}",
            }
        ),
        use_container_width=True,
    )


def render_downloads(
    figure: plt.Figure,
    tasks: pd.DataFrame,
    monthly_hours: pd.Series,
    file_format: str,
    filename: str,
    dpi: int,
    year: int,
    semester: int,
) -> None:
    """Render chart and CSV download buttons.

    Args:
        figure: Generated workload figure.
        tasks: Validated teaching position data.
        monthly_hours: Calculated monthly workload totals.
        file_format: Selected chart format.
        filename: Requested chart filename.
        dpi: PNG output resolution.
        year: Selected semester year.
        semester: Selected semester number.
    """
    st.subheader("Downloads")

    normalised_format = file_format.lower()

    chart_filename = create_safe_filename(
        filename,
        normalised_format,
    )

    chart_data = figure_to_bytes(
        figure,
        normalised_format,
        dpi,
    )

    task_filename = (
        f"teaching_positions_semester_{semester}_{year}.csv"
    )

    monthly_filename = (
        f"monthly_workload_semester_{semester}_{year}.csv"
    )

    download_columns = st.columns(3)

    with download_columns[0]:
        st.download_button(
            label=f"Download chart as {file_format}",
            data=chart_data,
            file_name=chart_filename,
            mime=get_chart_mime_type(file_format),
            use_container_width=True,
        )

    with download_columns[1]:
        st.download_button(
            label="Download teaching positions",
            data=tasks_to_csv(tasks),
            file_name=task_filename,
            mime="text/csv",
            use_container_width=True,
        )

    with download_columns[2]:
        st.download_button(
            label="Download monthly workload",
            data=monthly_workload_to_csv(monthly_hours),
            file_name=monthly_filename,
            mime="text/csv",
            use_container_width=True,
        )


def main() -> None:
    """Run the Streamlit teaching workload application."""
    st.title("📚 Teaching Workload Planner")

    st.write(
        "Configure your teaching positions using the editable table, "
        "then review the timeline and monthly workload distribution."
    )

    settings = render_semester_settings()

    year = int(settings["year"])
    semester = int(settings["semester"])
    semester_start = settings["semester_start"]
    semester_end = settings["semester_end"]

    initialise_session_state(
        year,
        semester,
    )

    with st.expander(
        "How workload is calculated",
        expanded=False,
    ):
        st.markdown(
            """
* Expected hours are distributed uniformly across every calendar day.
* The start and end dates are both included.
* Weekdays and weekends are treated equally.
* Monthly totals are calculated from the resulting daily workload.
* Average weekly workload uses the actual number of days in each month.
            """
        )

    edited_tasks = render_task_editor(
        year=year,
        semester=semester,
        semester_start=semester_start,
        semester_end=semester_end,
    )

    try:
        tasks = prepare_task_data(
            task_records=edited_tasks,
            semester_start=semester_start,
            semester_end=semester_end,
        )

        monthly_hours = calculate_monthly_workload(
            tasks=tasks,
            semester_start=semester_start,
            semester_end=semester_end,
        )
    except ValueError as error:
        st.error(str(error))
        st.info(
            "Correct the highlighted task configuration or add a "
            "teaching position to continue."
        )
        st.stop()

    st.divider()
    st.subheader("Workload summary")

    render_summary_metrics(
        tasks,
        monthly_hours,
    )

    st.subheader("Timeline and monthly workload")

    try:
        figure = plot_workload(
            tasks=tasks,
            monthly_hours=monthly_hours,
            semester_start=semester_start,
            semester_end=semester_end,
            semester=semester,
            title=DEFAULT_TITLE,
            workload_base_colour=DEFAULT_WORKLOAD_COLOUR,
            figure_size=(
                DEFAULT_FIGURE_WIDTH,
                DEFAULT_FIGURE_HEIGHT,
            ),
        )
    except (TypeError, ValueError) as error:
        st.error(
            "The chart could not be generated. "
            f"Details: {error}"
        )
        st.stop()

    st.pyplot(
        figure,
        use_container_width=True,
        dpi=DEFAULT_DISPLAY_DPI,
    )

    with st.expander(
        "View monthly workload table",
        expanded=False,
    ):
        render_monthly_table(monthly_hours)

    render_downloads(
        figure=figure,
        tasks=tasks,
        monthly_hours=monthly_hours,
        file_format="PNG",
        filename=(
            f"teaching_workload_semester_{semester}_{year}"
        ),
        dpi=DEFAULT_OUTPUT_DPI,
        year=year,
        semester=semester,
    )

    plt.close(figure)



if __name__ == "__main__":
    main()
