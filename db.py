import mysql.connector

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="taskmanagement"
    )

# print("Kết nối thành công!")

# conn.close()