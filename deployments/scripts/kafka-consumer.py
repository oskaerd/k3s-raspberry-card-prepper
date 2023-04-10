import time
from kafka import KafkaConsumer

if __name__ == "__main__":
    print("Running consumer")
    records = []
    topic_name = "books"

    consumer = KafkaConsumer(topic_name, auto_offset_reset='earliest',
                             bootstrap_servers=['192.168.0.100:19092'], api_version=(0, 10), consumer_timeout_ms=1000)
    for msg in consumer:
        message_text = msg.value
        records.append(message_text)
    consumer.close()
    time.sleep(5)

    print(records)
