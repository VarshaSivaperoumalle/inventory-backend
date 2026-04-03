from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os

# -------------------------------
# INIT APP
# -------------------------------
app = Flask(__name__)
CORS(app)

# -------------------------------
# DATABASE INIT
# -------------------------------
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

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
    return "Inventory Backend Running 🚀"

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

    return jsonify({"status": "success" if user else "fail"})

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

    # Default values if missing
    df['expiry_date'] = df.get('expiry_date', None)
    df['supplier'] = df.get('supplier', "Unknown")
    df['category'] = df.get('category', "General")

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
# CHATBOT (RULE-BASED)
# -------------------------------
@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get("message", "").lower()

    conn = sqlite3.connect('database.db')
    df = pd.read_sql_query("SELECT * FROM inventory", conn)
    conn.close()

    def contains(words):
        return any(word in user_msg for word in words)

    if contains(["low", "less", "minimum", "shortage"]):
        low = df[df['quantity'] < 15]
        if low.empty:
            return jsonify({"answer": "No items are low in stock"})
        return jsonify({
            "answer": low[['product_name','quantity']].to_dict(orient='records')
        })

    elif contains(["total items", "count"]):
        return jsonify({"answer": f"Total products: {len(df)}"})

    elif contains(["value", "worth"]):
        total = int((df['quantity'] * df['price']).sum())
        return jsonify({"answer": f"Total inventory value: ₹{total}"})

    return jsonify({
        "answer": "Ask about stock, value, recommendations, etc."
    })

# -------------------------------
# RUN SERVER (FIXED FOR DEPLOYMENT)
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
