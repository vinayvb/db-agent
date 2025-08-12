# SQL Query Agent with Natural Language Interface

This project provides a Python-based agent that allows you to ask natural language questions about your database schema. It translates your questions into SQL queries, runs them against an MCP server, and returns the results. The agent runs in a loop, allowing multiple queries until you press Ctrl+C to quit.

---
## DB Setup Instructions

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
   python sk_mcp_server.py

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
   * Give me all orders with more than 3 items
   * Show all customers who have ordered a product costing more than $40, and how many such products they ordered