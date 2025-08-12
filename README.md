# SQL Query Agent with Natural Language Interface

This project provides a Python-based agent that allows you to ask natural language questions about your database schema. It translates your questions into SQL queries, runs them against an MCP server, and returns the results. The agent runs in a loop, allowing multiple queries until you press Ctrl+C to quit.

---
## DB Setup Instructions
1. **Define Tables**
   ```bash
   CREATE TABLE customers (
     customer_id INT PRIMARY KEY,
     first_name VARCHAR(100),
     last_name VARCHAR(100),
     email VARCHAR(100),
     created_at DATETIME
   );
 
    CREATE TABLE products (
    product_id        INT PRIMARY KEY,
    name              VARCHAR(200),
    description       VARCHAR(500),
    price             DECIMAL,
    stock_quantity    INT
   );

   CREATE TABLE orders (
     order_id          INT PRIMARY KEY,
     customer_id       INT,
     order_date        DATETIME,
     status            VARCHAR(40)
   );

   CREATE TABLE order_items (
     order_item_id     INT PRIMARY KEY,
     order_id          INT,
     product_id        INT,
     quantity          INT,
     unit_price        DECIMAL
   );

2. **Insert Sample Data**
   ```bash
   INSERT INTO dbo.customers VALUES
     (1, 'Alice', 'Smith', 'alice@example.com', '2025-07-26'),
     (2, 'Bob', 'Jones', 'bob@example.com', '2025-07-26'),
     (3, 'Charlie', 'Brown', 'charlie@example.com', '2025-07-27');

   INSERT INTO dbo.products VALUES
     (1, 'Widget', 'Basic widget', 19.99, 100),
     (2, 'Gadget', 'Fancy gadget', 49.99, 50),
     (3, 'Thingamajig', 'Unused product', 29.99, 10);

   INSERT INTO dbo.orders VALUES
     (1, 1, '2025-07-26', 'Shipped'),
     (2, 2, '2025-07-26', 'Processing'),
     (3, 3, '2025-07-27', 'Processing'),
     (4, 2, '2025-07-27', 'Shipped');

   INSERT INTO dbo.order_items VALUES
     (1, 1, 1, 2, 19.99),
     (2, 1, 2, 1, 49.99),
     (3, 2, 1, 1, 19.99),
     (4, 3, 1, 1, 19.99),
     (5, 3, 2, 1, 49.99),
     (6, 4, 2, 2, 49.99);

## Code Setup Instructions

1. **Clone the repository:**

   ```bash
   git clone https://github.com/vinayvb/db-agent.git
   cd db-agent

2. **Create and activate a Python virtual environment named myenv:**
   ```bash
   python3 -m venv myenv
   source myenv/bin/activate    # On Windows use: myenv\Scripts\activate

3. **Install dependencies from requirements.txt**
   ```bash
   pip install -r requirements.txt

4. **Create a .env file in the root directory with the following variables 
   and put in the right values by replacing the placeholders:**
   ```bash
   HOST=your_db_host
   DATABASE=your_db_name
   APP_USER=your_db_user
   APP_PASSWORD=your_db_password
   AZURE_OPENAI_API_KEY=your_api_key
   AZURE_OPENAI_ENDPOINT=https://your_openai_endpoint_here
   MCP_SERVER_URL=http://localhost:8080/mcp
   
5. **Since the database is Serverless, it may be paused, 
   so start the database by logging into the Query Editor in the Portal**

6. **Run the MCP server first, so the agent can connect to it**
   ```bash
   python mcp_server.py

7. **Run the Python agent script:**
   ```bash
   python sk_agent.py
   
8. **Interact with the agent:**
   * Type your natural language question and press enter
   * To quit, press Cntrl+C

9. **Try the following sample questions**
   * What is the total amount each customer has spent
   * What is the average unit price of items ordered
   * show me all the orders along with customer name
   * list all products in order id 1
   * Determine what items Alice ordered
   * Determine what items Alice Smith ordered
   * List products that have never been ordered
   * Show me customers who ordered more than 1 product in total
   * Give me orders that include a product with price > 20
   * Show me top 5 expensive orders
   * Give me all orders with more than 2 items
   * Show all customers who have ordered a product costing more than $40, and how many such products they ordered