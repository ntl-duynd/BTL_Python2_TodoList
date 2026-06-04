import mysql.connector

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="taskmanagement"
)

print("Kết nối thành công!")

conn.close()