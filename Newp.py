import pymysql
import requests
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# הגדרות מסד הנתונים
DB_HOST = "localhost"
DB_USER = "username"
DB_PASSWORD = "password"
DB_NAME = "attendance_db"

# כתובת ה API של האפליקציה ושליחת דוחות למנהלים
APP_API_URL = "http://internal-server/api/update_attendance"
TASKS_API_URL = "http://internal-server/api/assign_tasks"
REPORTS_API_URL = "http://internal-server/api/send_daily_report"

# הגדרות דוא"ל לשליחה
SMTP_SERVER = "smtp.your-email-server.com"
SMTP_PORT = 587
SENDER_EMAIL = "your-email@example.com"
SENDER_PASSWORD = "your-email-password"

def connect_db():
    """יוצר חיבור למסד הנתונים"""
    return pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)

def fetch_attendance():
    """שליפת נתוני כניסה/יציאה משעון נוכחות"""
    return [
        {"employee_id": "12345", "timestamp": "2025-03-14 08:00:00", "status": "IN"},
        {"employee_id": "12346", "timestamp": "2025-03-14 16:30:00", "status": "OUT"},
    ]

def get_employee_tasks(employee_id):
    """שליפת משימות מותאמות לעובד"""
    conn = connect_db()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    sql = "SELECT task_id, task_name, due_time, status FROM tasks WHERE employee_id = %s AND status = 'pending'"
    cursor.execute(sql, (employee_id,))
    tasks = cursor.fetchall()

    cursor.close()
    conn.close()
    return tasks

def get_task_report(employee_id):
    """שליפת דוח ביצוע משימות לעובד (כולל משימות שלא הושלמו)"""
    conn = connect_db()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    sql = "SELECT task_id, task_name, status FROM tasks WHERE employee_id = %s AND status IN ('completed', 'pending')"
    cursor.execute(sql, (employee_id,))
    task_report = cursor.fetchall()

    cursor.close()
    conn.close()
    return task_report

def get_uncompleted_tasks(employee_id):
    """שליפת משימות שלא הושלמו לעובד"""
    conn = connect_db()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    sql = "SELECT task_id, task_name, due_time FROM tasks WHERE employee_id = %s AND status = 'pending'"
    cursor.execute(sql, (employee_id,))
    uncompleted_tasks = cursor.fetchall()

    cursor.close()
    conn.close()
    return uncompleted_tasks

def insert_attendance(records):
    """שמירת נתוני כניסה/יציאה במסד הנתונים"""
    conn = connect_db()
    cursor = conn.cursor()

    for record in records:
        sql = "INSERT INTO attendance (employee_id, timestamp, status) VALUES (%s, %s, %s)"
        cursor.execute(sql, (record["employee_id"], record["timestamp"], record["status"]))

    conn.commit()
    cursor.close()
    conn.close()

def send_to_app(records):
    """שליחת נתוני כניסה/יציאה ומשימות לאפליקציה"""
    for record in records:
        # שליחת נתוני נוכחות
        attendance_payload = {
            "employee_id": record["employee_id"],
            "timestamp": record["timestamp"],
            "status": record["status"]
        }
        response = requests.post(APP_API_URL, json=attendance_payload)

        if response.status_code == 200:
            print(f"עודכן באפליקציה: {record}")

            # אם העובד נכנס – לשלוח משימות מותאמות
            if record["status"] == "IN":
                tasks = get_employee_tasks(record["employee_id"])
                if tasks:
                    tasks_payload = {"employee_id": record["employee_id"], "tasks": tasks}
                    task_response = requests.post(TASKS_API_URL, json=tasks_payload)

                    if task_response.status_code == 200:
                        print(f"נשלחו משימות לעובד {record['employee_id']}")
                    else:
                        print(f"שגיאה בשליחת משימות: {task_response.status_code}")
        else:
            print(f"שגיאה בשליחה לאפליקציה: {response.status_code}")

def send_daily_reports():
    """שליחת דוחות ביצוע משימות למנהלים בסוף היום"""
    conn = connect_db()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    sql = "SELECT DISTINCT employee_id FROM tasks WHERE status IN ('completed', 'pending')"
    cursor.execute(sql)
    employees = cursor.fetchall()

    for employee in employees:
        employee_id = employee["employee_id"]
        task_report = get_task_report(employee_id)
        uncompleted_tasks = get_uncompleted_tasks(employee_id)

        if task_report:
            report_payload = {
                "employee_id": employee_id,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "completed_tasks": [task for task in task_report if task["status"] == "completed"],
                "uncompleted_tasks": uncompleted_tasks
            }

            # שליחה למנהל דרך ה-API
            response = requests.post(REPORTS_API_URL, json=report_payload)
            if response.status_code == 200:
                print(f"דוח נשלח למנהל עבור עובד {employee_id}")
            else:
                print(f"שגיאה בשליחת דוח: {response.status_code}")
                
            # שליחת דוח בדוא"ל
            send_report_via_email(employee_id, report_payload)

    cursor.close()
    conn.close()

def send_report_via_email(employee_id, report_payload):
    """שליחת דוח ביצוע משימות למנהל בדוא"ל"""
    # יצירת הודעת דוא"ל
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = "manager@example.com"  # כתובת המנהל
    msg['Subject'] = f"Daily Report for Employee {employee_id}"

    # יצירת תוכן הדוא"ל
    body = f"Daily Report for Employee {employee_id} - {datetime.now().strftime('%Y-%m-%d')}\n\n"
    body += "Completed Tasks:\n"
    for task in report_payload["completed_tasks"]:
        body += f"- {task['task_name']}\n"
    
    body += "\nUncompleted Tasks:\n"
    for task in report_payload["uncompleted_tasks"]:
        body += f"- {task['task_name']} (Due: {task['due_time']})\n"
    
    msg.attach(MIMEText(body, 'plain'))

    # שליחה דרך SMTP
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            text = msg.as_string()
            server.sendmail(SENDER_EMAIL, msg['To'], text)
            print(f"דוח נשלח למנהל בדוא\"ל עבור עובד {employee_id}")
    except Exception as e:
        print(f"שגיאה בשליחת דוא\"ל: {str(e)}")

def main():
    while True:
        records = fetch_attendance()
        if records:
            insert_attendance(records)
            send_to_app(records)
        
        # שליחת דוחות ביצוע בסיום יום עבודה
        current_time = datetime.now().strftime("%H:%M")
        if current_time == "17:00":  # שעה שמונה, למשל, לשלוח דוחות
            send_daily_reports()

        time.sleep(60)  # בדיקה כל דקה

if __name__ == "__main__":
    main()
