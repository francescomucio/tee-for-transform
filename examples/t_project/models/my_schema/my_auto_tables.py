from t4t.parser.model import model


@model(table_name="my_auto_table_one")
def auto_table_one():
    return "SELECT * FROM my_first_table"


    # return [{
    #     "id": "1",
    #     "name": "John Doe"
    # }, {
    #     "id": "2",
    #     "name": "Jane Doe"
    # }]