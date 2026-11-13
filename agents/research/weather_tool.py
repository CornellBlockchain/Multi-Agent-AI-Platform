# Takes a city name (like "Ithaca") and returns the current weather there.
# Uses Open-Meteo, a free weather service that needs no API key.
# get_weather() does the actual weather lookup
# run_weather_with_events() wraps it with "started/completed/failed" updates
# if __name__ == "__main__" lets you test it by typing a city in the terminal

import asyncio   # lets Python wait for websites without freezing
import json      # used at the bottom to print events nicely
import httpx     # the library that sends requests to websites

from uuid import uuid4   # makes random unique IDs

# This "if" just handles two different ways the file can be run.
# Either way, it loads create_tool_event from events.py.
if __package__:
    from events import create_tool_event
else:
    from events import create_tool_event

# The two Open-Meteo web addresses we'll call.
# Written in CAPITALS because they never change (a Python habit for constants).
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"   # city name -> coordinates
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"            # coordinates -> weather


# It takes a location (text) and gives back a dictionary
async def get_weather(location: str) -> dict:
    """Look up a place and return its current weather."""
    # .strip() removes extra spaces, so "  Ithaca  " becomes "Ithaca"
    location = location.strip()
    # If the user typed nothing, stop right away with a clear error
    if not location:
        raise ValueError("The location cannot be empty.")
    # timeout=20.0 means "give up if a website takes more than 20 seconds"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            GEOCODING_URL,
            params={
                "name": location,   # the city to look up
                "count": 1,         # only give us the single best match
            },
        )

        # If the website sent back an error (like 404 or 500), stop here.
        # This "raises" an error that part 2 will catch and report.
        response.raise_for_status()

        # Turn the website's JSON answer into a Python dictionary,
        # then grab the "results" list. If there's no "results" key
        # (city not found), use an empty list [] instead of crashing.
        places = response.json().get("results", [])

        # Empty list = no city with that name exists.
        # This is NOT an error, just "no match", so we return a normal result.
        if not places:
            return {
                "message": "No matching location found.",
                "summary": f"Could not find a place called '{location}'.",
                "sources": [],
                "artifacts": [],
            }

        # Take the first (best) match from the list
        place = places[0]

        # Build a readable name like "Ithaca, New York, United States".
        # .get() returns None if a piece is missing (some places have no state),
        # and "if part" skips any missing pieces so we don't print "None".
        place_name = ", ".join(
            part for part in [place["name"], place.get("admin1"), place.get("country")]
            if part
        )

        # Now that we know WHERE the city is, ask for the weather there.
        response = await client.get(
            FORECAST_URL,
            params={
                # Coordinates we got from request 1
                "latitude": place["latitude"],
                "longitude": place["longitude"],

                # Which measurements we want right now (comma-separated):
                #   temperature_2m        = temperature 2 meters above ground
                #   apparent_temperature  = "feels like" temperature
                #   relative_humidity_2m  = humidity %
                #   precipitation         = rain/snow amount
                #   wind_speed_10m        = wind speed 10 meters up
                "current": "temperature_2m,apparent_temperature,"
                           "relative_humidity_2m,precipitation,wind_speed_10m",

                # US units instead of the default metric ones
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",

                # Show the time in the city's own local time zone
                "timezone": "auto",
            },
        )
        response.raise_for_status()
        data = response.json()

    # Open-Meteo sends back two dictionaries we care about the data and the units
    now = data["current"]
    units = data["current_units"]

    # Build a readable multi-line description.
    # The f"..." strings let us drop variables in using {curly braces}.
    # \n means "new line"
    summary = (
        f"Weather in {place_name} (observed {now['time']} local time):\n"
        f"Temperature: {now['temperature_2m']}{units['temperature_2m']} "
        f"(feels like {now['apparent_temperature']}{units['apparent_temperature']})\n"
        f"Humidity: {now['relative_humidity_2m']}{units['relative_humidity_2m']}\n"
        f"Wind: {now['wind_speed_10m']} {units['wind_speed_10m']}\n"
        f"Precipitation: {now['precipitation']} {units['precipitation']}"
    )

    # Return the 4 keys EVERY tool in this project must return:
    return {
        "message": f"Got current weather for {place_name}.",  # short update for the dashboard
        "summary": summary,                                   # the actual findings
        "sources": [{                                         # where the info came from
            "title": "Open-Meteo",
            "url": "https://open-meteo.com/",
        }],
        "artifacts": [],                                
    }


# Runs get_weather() but sends live updates before and after:
# "Checking weather for Ithaca" becomes "Got current weather for Ithaca..." so the user can see this tool working and their command isn't frozen.
async def run_weather_with_events(
        location: str,   # the city to look up
        run_id: str,     # ID of the overall question (given to us by the backend)
        task_id: str,    # ID of the research agent's job (given to us by the backend)
        events: list,    # a list we add every update to
) -> dict:
    """Run the weather tool and send live updates to the dashboard."""
    # The "events" list is where we save each update for the dashboard.
    # The backend needs to send them to the frontend so the user can see them.

    tool_call_id = str(uuid4())

# A small helper function that creates one update and saves it.
    def emit(event_type: str, message: str):
        event = create_tool_event(          # builds the update (from events.py)
            run_id=run_id,
            task_id=task_id,
            tool_call_id=tool_call_id,
            event_type=event_type,          # "tool.started", "tool.completed", or "tool.failed"
            message=message,                # the text the dashboard shows
            tool="weather",                 # tells the dashboard which tool this is
        )
        events.append(event)                # save it to the list
        print(f"[{event_type}] {message}", flush=True)   # also print it right away

    emit("tool.started", f"Checking weather for {location}")

    try:
        # Actually do the lookup. "await" = wait for it to finish.
        result = await get_weather(location)

    except asyncio.CancelledError:
        # Someone stopped the tool partway through
        emit("tool.failed", "Weather lookup was cancelled")
        raise   # pass the error along so whoever called us knows

    except Exception:
        # Anything else went wrong (website down, no internet, etc.)
        emit("tool.failed", "Weather lookup failed")
        raise

    else:
        # This runs only if NO error happened.
        emit("tool.completed", result["message"])
        return result

#TEST FOR THE FIRST PART OF JUST GETTING WEATHER
if __name__ == "__main__":
    result = asyncio.run(get_weather("Ithaca"))   # run only Part 1
    print(result["summary"])

#TEST FOR THE SECOND PART OF RUNNING WEATHER WITH EVENTS AND UPDATES OF STARTED/COMPLETED/FAILED
if __name__ == "__main__":
    print("Test 1:real city")
    events = []
    result = asyncio.run(
        run_weather_with_events("Ithaca", "local-run", "local-task", events)
    )
    print(result["summary"])
    print(json.dumps(events, indent=2))

    print("Test 2:fake city")

    events = []
    result = asyncio.run(
        run_weather_with_events("whakjs", "local-run", "local-task", events)
    )
    print(result["summary"])
    print(json.dumps(events, indent=2))
    #for the fake city, we expect a ValueError to be raised, so we catch it and print it out
    print("Test 3: empty city")
    events = []
    try:
        asyncio.run(
            run_weather_with_events("", "local-run", "local-task", events)
        )
    except ValueError as error:
        print(f"Got the expected error: {error}")
    print(json.dumps(events, indent=2))
