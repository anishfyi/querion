# Example questions

Querion is platform agnostic, so phrase questions in your own domain. A few
shapes that work well:

## Trends and comparisons
- "Revenue by week for the last 8 weeks, with a chart."
- "New vs returning customers this month versus last month."
- "Average order value by month this year."

## Rankings
- "Top 10 products by revenue this quarter."
- "Which customers spent the most in the last 90 days?"

## Live status (HTTP sources)
- "What is the live status of order 14377?"
- "How many open invoices does customer 88 have right now?"

## Cross-source
- "Compare this month's orders in the database with the live count from the API."
- "Which orders in Postgres are still marked open but show paid in the API?"

## Things Querion will refuse
- "Cancel order 14377." (write)
- "Update the price of SKU X." (write)
- "Delete the test customers." (write)

Asking Querion to change data is refused by the firewall. Asking ABOUT past
changes ("which orders were cancelled last week?") is normal analytics.
