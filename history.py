

import sqlite3
import datetime
from utils import paginate_output

DB_FILE = "food_log.db"

def get_meals_for_date(date_str):
    """
    Retrieves and displays all food entries for a specific date.
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        print("Invalid date format. Please use YYYY-MM-DD.")
        return

    start_date = datetime.datetime.combine(date, datetime.time.min).isoformat()
    end_date = datetime.datetime.combine(date, datetime.time.max).isoformat()

    c.execute(
        """
        SELECT timestamp, food_item, quantity, quantity_unit, calories, protein, carbs, fat
        FROM food_log
        WHERE timestamp >= ? AND timestamp < ?
        ORDER BY timestamp
        """,
        (start_date, end_date),
    )
    meals = c.fetchall()
    conn.close()

    if meals:
        output = f"--- Meals for {date.strftime('%Y-%m-%d')} ---\n"
        for meal in meals:
            timestamp, food_item, quantity, quantity_unit, calories, protein, carbs, fat = meal
            output += f"\n- {food_item} ({quantity}{quantity_unit}) - {calories:.2f} kcal\n"
            output += f"  Protein: {protein:.2f}g, Carbs: {carbs:.2f}g, Fat: {fat:.2f}g\n"
            output += f"  Logged at: {datetime.datetime.fromisoformat(timestamp).strftime('%H:%M:%S')}\n"
        paginate_output(output)
    else:
        print(f"No meals found for {date.strftime('%Y-%m-%d')}")


