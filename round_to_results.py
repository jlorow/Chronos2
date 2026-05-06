import json
import os
import glob

# Paths relative to this script's location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROUNDS_FOLDER = os.path.join(BASE_DIR, "rounds")
RESULTS_FILE = os.path.join(BASE_DIR, "results.json")

def get_latest_round_file():
    """Get the most recently modified round_*.json file"""
    pattern = os.path.join(ROUNDS_FOLDER, "round_*.json")
    files = glob.glob(pattern)

    if not files:
        return None

    # Sort by modification time, newest first
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

def convert(round_filepath):
    """Convert round json → results.json format"""
    with open(round_filepath, "r") as f:
        round_data = json.load(f)

    matches = sorted(round_data["matches"], key=lambda m: m["row"])

    results = [m["result"] for m in matches]
    scores  = [m["score"]  for m in matches]

    return {"results": results, "scores": scores}

def run():
    latest = get_latest_round_file()

    if not latest:
        print(f"❌ No round files found in: {ROUNDS_FOLDER}")
        return

    print(f"📄 Latest round file: {os.path.basename(latest)}")

    output = convert(latest)

    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"✅ results.json updated ({len(output['results'])} matches)")
    print(f"   Results : {output['results']}")
    print(f"   Scores  : {output['scores']}")

run()
