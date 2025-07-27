import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
import os
import sqlite3
import datetime
import sys
import argparse
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSequence
from langchain_core.output_parsers import StrOutputParser
from .cache import get_from_cache, add_to_cache
from .history import get_meals_for_date
from .utils import paginate_output
import json
from dotenv import load_dotenv

def setup_environment():
    """
    Checks for a .env file and prompts the user to create one if it doesn't exist.
    """
    if not os.path.exists('.env'):
        print("The .env file is not found.")
        print("Please provide the following information:")
        
        openai_api_key = input("Enter your OpenAI API key: ")
        openai_base_url = input("Enter the OpenAI base URL (or press Enter for default): ")
        openai_model = input("Enter the OpenAI model name (or press Enter for default): ")
        
        with open('.env', 'w') as f:
            f.write(f"OPENAI_API_KEY={openai_api_key}\n")
            if openai_base_url:
                f.write(f"OPENAI_BASE_URL={openai_base_url}\n")
            if openai_model:
                f.write(f"OPENAI_MODEL={openai_model}\n")
        
        print("\n.env file created successfully.")
        print("Please restart the application to use the new settings.")
        sys.exit(0)

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL")

# --- Database Setup ---
DB_FILE = "food_log.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS food_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            food_item TEXT NOT NULL,
            quantity REAL NOT NULL,
            quantity_unit TEXT NOT NULL,
            calories REAL NOT NULL,
            protein REAL NOT NULL,
            carbs REAL NOT NULL,
            fat REAL NOT NULL
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            total_calories REAL NOT NULL,
            total_protein REAL NOT NULL,
            total_carbs REAL NOT NULL,
            total_fat REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

# --- LLM Setup ---
llm_params = {
    "api_key": OPENAI_API_KEY,
    "temperature": 0.1
}

if OPENAI_BASE_URL:
    llm_params["base_url"] = OPENAI_BASE_URL

if OPENAI_MODEL:
    llm_params["model"] = OPENAI_MODEL

llm = None
if OPENAI_API_KEY:
    llm = ChatOpenAI(**llm_params)

# -------------------------------------------------------------
# Fixed prompt template: only expects {user_input}
# -------------------------------------------------------------
example_json = {
    "food_item": "bolo de banana",
    "quantity": 175,
    "quantity_unit": "g",
    "calories_per_100g": 300,
    "protein_per_100g": 4,
    "carbs_per_100g": 40,
    "fat_per_100g": 14
}
example_str = json.dumps(example_json)

prompt_template = ChatPromptTemplate.from_messages(
    [
        ("system",
         "You are a helpful assistant that extracts nutritional information from text. "
         "Respond with only a valid JSON object."),
        ("human",
         "Extract the food item, quantity, and quantity unit from the following text. "
         "Then, estimate the calories, protein, carbohydrates, and fat for that food item per 100g. "
         'Return the result as a JSON object with the keys: "food_item", "quantity", '
         '"quantity_unit", "calories_per_100g", "protein_per_100g", "carbs_per_100g", "fat_per_100g".'),
        ("human", f'Example: Text: "comi 175g de bolo de banana" Output: {example_str.replace("{", "{{").replace("}", "}}")}'),
        ("human", "{user_input}"),
    ]
)

chain = None
if llm:
    chain = prompt_template | llm | StrOutputParser()

# --- Main Application Logic ---
def log_food(text_input):
    """
    Parses natural language input, gets nutritional info, and logs it.
    """
    if not chain:
        print("LLM not initialized. Please check your API key.")
        return
        
    try:
        response_str = chain.invoke({"user_input": text_input})
        # Clean the response string by removing markdown formatting
        if '```json' in response_str:
            response_str = response_str.split('```json')[1].split('```')[0].strip()
        response_data = json.loads(response_str)

        food_item = response_data["food_item"]
        quantity = response_data["quantity"]
        quantity_unit = response_data["quantity_unit"]

        # Check cache first
        cached_nutrition = get_from_cache(food_item)

        if cached_nutrition:
            print("\n(🎯)")
            nutrition_per_100g = cached_nutrition
        else:
            nutrition_per_100g = {
                "calories": response_data["calories_per_100g"],
                "protein": response_data["protein_per_100g"],
                "carbs": response_data["carbs_per_100g"],
                "fat": response_data["fat_per_100g"],
            }
            add_to_cache(food_item, nutrition_per_100g)

        # Calculate nutrition for the given quantity
        multiplier = quantity / 100.0
        calculated_nutrition = {
            "food_item": food_item,
            "quantity": quantity,
            "quantity_unit": quantity_unit,
            "calories": nutrition_per_100g["calories"] * multiplier,
            "protein": nutrition_per_100g["protein"] * multiplier,
            "carbs": nutrition_per_100g["carbs"] * multiplier,
            "fat": nutrition_per_100g["fat"] * multiplier,
        }

        print("\n--- Nutrition Estimation ---")
        print(f"Food: {calculated_nutrition['food_item']}")
        print(f"Quantity: {calculated_nutrition['quantity']} {calculated_nutrition['quantity_unit']}")
        print(f"Calories: {calculated_nutrition['calories']:.2f} kcal")
        print(f"Protein: {calculated_nutrition['protein']:.2f}g")
        print(f"Carbs: {calculated_nutrition['carbs']:.2f}g")
        print(f"Fat: {calculated_nutrition['fat']:.2f}g")
        print("--------------------------")

        confirm = input("Is this correct? (y/n): ").lower()

        if confirm == "y":
            save_entry(calculated_nutrition)
            print("✅ Food entry saved!")
        else:
            print("❌ Entry discarded.")

    except Exception as e:
        print(f"Error: Could not process input. {e}")


def save_entry(data):
    """
    Saves a food entry to the database.
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO food_log (timestamp, food_item, quantity, quantity_unit, calories, protein, carbs, fat)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.datetime.now().isoformat(),
            data["food_item"],
            data["quantity"],
            data["quantity_unit"],
            data["calories"],
            data["protein"],
            data["carbs"],
            data["fat"],
        ),
    )
    conn.commit()
    conn.close()


def save_todays_summary(summary_data):
    """
    Saves or updates today's summary in the daily_summary table.
    """
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO daily_summary (date, total_calories, total_protein, total_carbs, total_fat)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            today_date,
            summary_data[0],
            summary_data[1],
            summary_data[2],
            summary_data[3],
        ),
    )
    conn.commit()
    conn.close()


def get_summary_for_date(date_str):
    """
    Retrieves and displays the summary for a specific date.
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        print("Invalid date format. Please use YYYY-MM-DD.")
        return

    c.execute(
        """
        SELECT total_calories, total_protein, total_carbs, total_fat
        FROM daily_summary
        WHERE date = ?
        """,
        (date.isoformat(),),
    )
    summary = c.fetchone()
    conn.close()

    if summary:
        output = f"--- Summary for {date.strftime('%Y-%m-%d')} ---\n"
        output += f"Total Calories: {summary[0]:.2f} kcal\n"
        output += f"Total Protein: {summary[1]:.2f}g\n"
        output += f"Total Carbs: {summary[2]:.2f}g\n"
        output += f"Total Fat: {summary[3]:.2f}g"
        paginate_output(output)
    else:
        print(f"No summary found for {date.strftime('%Y-%m-%d')}")


def get_todays_summary():
    """
    Retrieves and displays the summary of today's food entries.
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + datetime.timedelta(days=1)

    c.execute(
        """
        SELECT
            SUM(calories),
            SUM(protein),
            SUM(carbs),
            SUM(fat)
        FROM food_log
        WHERE timestamp >= ? AND timestamp < ?
        """,
        (today_start.isoformat(), today_end.isoformat()),
    )

    summary = c.fetchone()
    conn.close()

    print("\n--- Today's Summary ---")
    if summary and summary[0] is not None:
        save_todays_summary(summary)
        print(f"Total Calories: {summary[0]:.2f} kcal")
        print(f"Total Protein: {summary[1]:.2f}g")
        print(f"Total Carbs: {summary[2]:.2f}g")
        print(f"Total Fat: {summary[3]:.2f}g")
    else:
        print("No entries for today.")
    print("-----------------------")


def remove_last_entry():
    """
    Removes the last food entry for today from the database.
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + datetime.timedelta(days=1)

    # Find the last entry for today
    c.execute(
        """
        SELECT id, food_item, quantity, quantity_unit FROM food_log
        WHERE timestamp >= ? AND timestamp < ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (today_start.isoformat(), today_end.isoformat()),
    )
    last_entry = c.fetchone()

    if last_entry:
        entry_id, food_item, quantity, quantity_unit = last_entry
        print(f"Removing last entry: {quantity}{quantity_unit} of {food_item}...")

        # Delete the entry
        c.execute("DELETE FROM food_log WHERE id = ?", (entry_id,))
        conn.commit()

        print("✅ Entry removed.")

        # Recalculate and display today's summary
        print("Updating summary...")
        get_todays_summary()

    else:
        print("No entries for today to remove.")

    conn.close()


def main():
    """
    Main function to run the CLI.
    """
    init_db()

    parser = argparse.ArgumentParser(description="Calorie and Macro Tracker CLI.")
    parser.add_argument(
        "-r", "--remove",
        metavar='ITEM',
        type=str,
        help="Remove an entry. Currently only 'last' is supported to remove the last entry of the day."
    )

    # New argument for logging food
    parser.add_argument(
        "food_input",
        nargs='?',
        default=None,
        help="Log a new food entry from the command line (e.g., '100g of chicken breast')."
    )
    
    parser.add_argument(
        '--setup',
        action='store_true',
        help="Set up the application by creating a .env file."
    )

    args = parser.parse_args()
    
    if args.setup:
        setup_environment()
        return

    if args.remove:
        if args.remove == 'last':
            remove_last_entry()
        else:
            print(f"Unsupported remove argument: {args.remove}. Only 'last' is supported.")
        return
    
    if args.food_input:
        log_food(args.food_input)
        return

    # Interactive mode if no arguments are given
    while True:
        print("\nWhat would you like to do?")
        print("1. ✍️ Log a new food entry")
        print("2. 📊 Show today's summary")
        print("3. 📅 Show summary for a specific date")
        print("4. 📜 View meals for a specific date")
        print("5. 🚪 Exit")
        choice = input("> ")
        if choice == "1":
            food_input = input("Enter food entry (e.g., 'comi 100g de frango'): ")
            log_food(food_input)
        elif choice == "2":
            get_todays_summary()
        elif choice == "3":
            date_input = input("Enter date (YYYY-MM-DD): ")
            get_summary_for_date(date_input)
        elif choice == "4":
            date_input = input("Enter date (YYYY-MM-DD): ")
            get_meals_for_date(date_input)
        elif choice == "5":
            break
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main()

