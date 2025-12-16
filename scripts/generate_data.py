from datetime import datetime
import json


for i in range(1):
    record = {
        "event": "{'event_number': " + str(i) + "}",
        "source": f"test_source_{i % 2}",
        "sourcetype": f"test_sourcetype_{i % 2}",
        "host": f"test_host_{i % 2}",
        "time": datetime.now().timestamp(),
        "index": "test_index",
        "fields": {
            "field1": f"value1_{i % 1}",
            "field2": f"value2_{i % 2}",
            "field3": f"value2_{i % 2}",  # lets try reusing the values
            "list": [f"item1_{i}", f"item2_{i}"],
            "one_item_list": [f"only_item_{i}"],
        },
    }

    print(json.dumps(record))

new_fields = {f"many_fields_{x}": f"value_{x}" for x in range(300)}
record["fields"] = new_fields
print(json.dumps(record))

new_fields = {f"big_field_{x}": "A" * 5000 for x in range(5)}
record["fields"] = new_fields
print(json.dumps(record))

new_fields = {"long_list": [f"long_list_item_{x}" for x in range(1000)]}
record["fields"] = new_fields
print(json.dumps(record))
