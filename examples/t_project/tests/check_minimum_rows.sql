-- Check that a table has at least a minimum number of rows
-- This test accepts a 'min_rows' parameter (defaults to 10)
-- Returns rows when test fails (0 rows = pass, 1+ rows = fail)
--
-- Usage: {"name": "check_minimum_rows", "params": {"min_rows": 5}}

SELECT 1 as violation
FROM @table_name
GROUP BY 1
HAVING COUNT(*) < @min_rows:10
