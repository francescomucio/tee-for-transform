-- Singular SQL test for my_first_table
-- This test checks that the 'name' column doesn't contain 'invalid' values
-- Returns rows when test fails (0 rows = pass, 1+ rows = fail)
-- Note: Table name is hardcoded - this is a singular SQL test for my_schema.my_first_table

SELECT id, name
FROM my_schema.my_first_table
WHERE name LIKE '%invalid%'
