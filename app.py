from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import sqlite3
import openai
import os

# -------------------------------
# INIT APP
# -------------------------------
app = Flask(__name__)
CORS(app)

# -------------------------------
# OPENAI API KEY
# -------------------------------
openai.api_key = ""   # 🔥 Replace with your key

# -------------------------------
# DATABASE INIT
# -------------------------------
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Inventory table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT,
        category TEXT,
        quantity INTEGER,
        price REAL,
        supplier TEXT,
        date_added TEXT,
        expiry_date TEXT
    )
    ''')

    # User table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        password TEXT
    )
    ''')

    # Default user
    cursor.execute("SELECT * FROM users WHERE username='admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                       ('admin', '1234'))

    conn.commit()
    conn.close()

init_db()

# -------------------------------
# HOME
# -------------------------------
@app.route('/')
def home():
    return "Inventory Backend Running"

# -------------------------------
# LOGIN
# -------------------------------
@app.route('/login', methods=['POST'])
def login():
    data = request.json

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    user = cursor.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (data['username'], data['password'])
    ).fetchone()

    conn.close()

    if user:
        return jsonify({"status": "success"})
    else:
        return jsonify({"status": "fail"})

# -------------------------------
# CSV UPLOAD
# -------------------------------
@app.route('/upload', methods=['POST'])
def upload_csv():
    file = request.files['file']

    try:
        df = pd.read_csv(file)
    except:
        df = pd.read_csv(file, encoding='latin1')

    df.dropna(subset=['product_name', 'quantity'], inplace=True)
    df['quantity'] = df['quantity'].astype(int)

    if 'expiry_date' not in df.columns:
        df['expiry_date'] = None

    if 'supplier' not in df.columns:
        df['supplier'] = "Unknown"

    if 'category' not in df.columns:
        df['category'] = "General"

    conn = sqlite3.connect('database.db')
    df.to_sql('inventory', conn, if_exists='append', index=False)
    conn.close()

    return jsonify({"message": "Inventory uploaded successfully"})

# -------------------------------
# FETCH INVENTORY
# -------------------------------
@app.route('/inventory', methods=['GET'])
def get_inventory():
    conn = sqlite3.connect('database.db')
    df = pd.read_sql_query("SELECT * FROM inventory", conn)
    conn.close()

    return df.to_json(orient='records')

# -------------------------------
# SUMMARY
# -------------------------------
@app.route('/summary', methods=['GET'])
def summary():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    result = cursor.execute("""
        SELECT category, SUM(quantity)
        FROM inventory
        GROUP BY category
    """).fetchall()

    conn.close()

    return jsonify(result)

# -------------------------------
# LOW STOCK
# -------------------------------
@app.route('/low-stock', methods=['GET'])
def low_stock():
    conn = sqlite3.connect('database.db')
    df = pd.read_sql_query("SELECT * FROM inventory", conn)
    conn.close()

    low_items = df[df['quantity'] < 15]
    return low_items.to_json(orient='records')

# -------------------------------
# RECOMMENDATION
# -------------------------------
@app.route('/recommend', methods=['GET'])
def recommend():
    conn = sqlite3.connect('database.db')
    df = pd.read_sql_query("SELECT * FROM inventory", conn)
    conn.close()

    avg_quantity = df.groupby('product_name')['quantity'].mean()

    recommendations = {
        product: int(qty * 1.5)
        for product, qty in avg_quantity.items()
    }

    return jsonify(recommendations)

# -------------------------------
# AI CHATBOT (OPENAI)
# -------------------------------
@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get("message").lower()

    conn = sqlite3.connect('database.db')
    df = pd.read_sql_query("SELECT * FROM inventory", conn)
    conn.close()

    # 🔹 HELP FUNCTION
    def contains(words):
        return any(word in user_msg for word in words)

    # 🔹 LOW STOCK
    if contains(["low", "less", "minimum", "running out", "shortage"]):
        low = df[df['quantity'] < 15]
        if low.empty:
            return jsonify({"answer": "Good news! No items are currently low in stock 😊"})
        return jsonify({
            "answer": f"⚠ These items are running low:\n{low[['product_name','quantity']].to_string(index=False)}"
        })

    # 🔹 TOTAL ITEMS
    elif contains(["total items", "how many items", "count"]):
        return jsonify({"answer": f"There are {len(df)} products in your inventory."})

    # 🔹 TOTAL VALUE
    elif contains(["total value", "inventory value", "worth"]):
        total = int((df['quantity'] * df['price']).sum())
        return jsonify({"answer": f"💰 Your total inventory value is approximately ₹{total}."})

    # 🔹 HIGHEST STOCK
    elif contains(["highest", "maximum", "most stock"]):
        item = df.loc[df['quantity'].idxmax()]
        return jsonify({
            "answer": f"📈 {item['product_name']} has the highest stock with {item['quantity']} units."
        })

    # 🔹 LOWEST STOCK
    elif contains(["lowest", "minimum stock"]):
        item = df.loc[df['quantity'].idxmin()]
        return jsonify({
            "answer": f"📉 {item['product_name']} has the lowest stock with only {item['quantity']} units."
        })

    # 🔹 CATEGORY COUNT
    elif contains(["categories", "how many categories"]):
        count = df['category'].nunique()
        return jsonify({"answer": f"You have {count} different categories in your inventory."})

    # 🔹 CATEGORY ANALYSIS
    elif contains(["category wise", "category stock"]):
        summary = df.groupby('category')['quantity'].sum()
        return jsonify({
            "answer": f"📊 Category-wise stock:\n{summary.to_string()}"
        })

    # 🔹 RECOMMENDATION
    elif contains(["recommend", "restock", "suggest"]):
        df['suggested'] = (df['quantity'] * 1.5).astype(int)
        return jsonify({
            "answer": f"📦 Suggested restock quantities:\n{df[['product_name','suggested']].to_string(index=False)}"
        })

    # 🔹 EXPENSIVE
    elif contains(["expensive", "costly", "highest price"]):
        item = df.loc[df['price'].idxmax()]
        return jsonify({
            "answer": f"💎 {item['product_name']} is the most expensive item priced at ₹{item['price']}."
        })

    # 🔹 CHEAPEST
    elif contains(["cheap", "lowest price"]):
        item = df.loc[df['price'].idxmin()]
        return jsonify({
            "answer": f"💸 {item['product_name']} is the cheapest item priced at ₹{item['price']}."
        })

    # 🔹 SUMMARY
    elif contains(["summary", "overview", "report"]):
        total_items = len(df)
        total_value = int((df['quantity'] * df['price']).sum())
        categories = df['category'].nunique()

        return jsonify({
            "answer": f"""📊 Inventory Summary:
- Total Items: {total_items}
- Categories: {categories}
- Total Value: ₹{total_value}"""
        })

    # 🔹 PRODUCT SEARCH
    else:
        for name in df['product_name']:
            if name.lower() in user_msg:
                item = df[df['product_name'] == name].iloc[0]
                return jsonify({
                    "answer": f"""🔍 Product Details:
Name: {item['product_name']}
Category: {item['category']}
Quantity: {item['quantity']}
Price: ₹{item['price']}"""
                })

    # 🔹 DEFAULT RESPONSE
    return jsonify({
        "answer": "🤖 I can help with stock levels, product details, inventory value, and recommendations. Try asking something like 'Which items are low?' 😊"
    })
# -------------------------------
# RUN SERVER
# -------------------------------
if __name__ == "__main__":
    app.run(debug=True)
