import sqlite3

# Connect to SQLite (in memory for testing)
conn = sqlite3.connect(':memory:')

# this is important because foreign keys are OFF by default in SQLite
conn.execute("PRAGMA foreign_keys = ON;")

cursor = conn.cursor()

# Helper function to inspect table contents
def print_table(cursor, table_name):
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    print(f"\nTable: {table_name}")
    print(" | ".join(columns))
    print("-" * 30)

    for row in rows:
        print(" | ".join(str(value) for value in row))

# Create tables
cursor.execute("""
CREATE TABLE student (
    student_id INT PRIMARY KEY,
    name TEXT NOT NULL,
    age INT
)
""")
cursor.execute("""
CREATE TABLE registered_courses  (
    student_id INT,
    course_id INT,
    PRIMARY KEY(student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES student(student_id)
               
)
""")
cursor.execute("""
CREATE TABLE grades (
    student_id INT,
    course_id INT,
    grade REAL,
    PRIMARY KEY(student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES student(student_id)
)
""")

students = [
    (1, 'Alice', 20),
    (2, 'Bob', 22),
    (3, 'Charlie', 21)
]
courses = [
    (1,370),
    (2,670),
    (3,390)
]
grades_data= [
    (1,370,89.5),
    (1,490,99),
    (2,431,57),
    (2,670,74),
    (3,390,97)
]

cursor.executemany("INSERT INTO student VALUES (?, ?, ?)", students)
cursor.executemany("INSERT INTO registered_courses VALUES (?, ?)",courses)
cursor.executemany("INSERT INTO grades VALUES (?, ?, ?)", grades_data)

conn.commit()

print_table(cursor, "student")

# Example SELECT query
cursor.execute("SELECT * FROM student")
print("\nResult of: SELECT * FROM student")
for row in cursor.fetchall():
    print(row)
cursor.execute("""
SELECT student_id, course_id, grade
FROM grades g
WHERE grade = (
    SELECT MAX(g2.grade)
    FROM grades g2
    WHERE g2.student_id = g.student_id
)
ORDER BY student_id;
""")

print("\nMaximum grade per student:")
for row in cursor.fetchall():
    print(row)


cursor.execute("""
SELECT student_id, AVG(grade) as average_grade
FROM grades
GROUP BY student_id
""")

print("\nAverage Grade per Student:")
for row in cursor.fetchall():
    print(row)

conn.close()