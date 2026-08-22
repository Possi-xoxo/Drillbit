"""Authoritative Drillbit release identity."""

APP_NAME="Drillbit"
APP_VERSION="1.0.0"
PROJECT_EXTENSION=".drillbit"
PROJECT_DESCRIPTION="Drillbit Project"


def about_text():
    return (f"{APP_NAME}\n"
            f"Version {APP_VERSION}\n\n"
            "Create, edit, and export DMC diamond-art patterns.\n\n"
            f"Native project format: {PROJECT_EXTENSION}")
