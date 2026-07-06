-- Example custom SQL test
-- This test checks that a table has at least 5 rows
-- Returns rows when test fails (0 rows = pass, 1+ rows = fail)
-- The table_name variable is automatically substituted
--
-- This query returns 1 row if the table has fewer than 5 rows (test fails)
-- This query returns 0 rows if the table has 5+ rows (test passes)

SELECT 1 as violation
FROM @table_name
GROUP BY 1
HAVING COUNT(*) < 5
