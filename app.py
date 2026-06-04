from flask import Flask, render_template, request, redirect, url_for, session
from datetime import timedelta
import random
import string
from db import get_connection

app = Flask(__name__)

app.secret_key = "task_manager_secret"
app.permanent_session_lifetime = timedelta(minutes=30)


@app.route("/")
def home():

    if "userID" in session:
        return redirect(url_for("index"))
    
    return redirect(url_for("login"))

@app.route("/index")
def index():

    if "userID" not in session:
        return redirect(url_for("login"))

    userID = session["userID"]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Thông tin user
    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE userID = %s
        """,
        (userID,)
    )

    user = cursor.fetchone()

    # Các group user tham gia
    cursor.execute(
        """
        SELECT
            g.groupID,
            g.groupName,
            gm.isGroupAdmin
        FROM groups g
        JOIN groupmembers gm
            ON g.groupID = gm.groupID
        WHERE gm.userID = %s
        ORDER BY g.groupName
        """,
        (userID,)
    )

    groups = cursor.fetchall()

    groups_with_tasks = []

    for group in groups:

        cursor.execute(
            """
            SELECT
                t.*
            FROM tasks t
            WHERE t.groupID = %s
            ORDER BY t.deadline
            """,
            (group["groupID"],)
        )

        tasks = cursor.fetchall()

        group_data = {
            "groupID": group["groupID"],
            "groupName": group["groupName"],
            "isGroupAdmin": group["isGroupAdmin"],
            "tasks": tasks
        }

        groups_with_tasks.append(group_data)

    cursor.close()
    conn.close()

    return render_template(
        "index.html",
        user=user,
        groups_with_tasks=groups_with_tasks
    )

@app.route("/login", methods=["GET", "POST"])
def login():

    # Nếu đã đăng nhập thì không cho vào login nữa
    if "userID" in session:
        return redirect(url_for("index"))

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT *
        FROM Users
        WHERE email = %s
        AND password = %s
        """

        cursor.execute(sql, (email, password))

        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user:

            session.permanent = True

            session["userID"] = user["userID"]
            session["userName"] = user["userName"]
            session["email"] = user["email"]

            return redirect(url_for("index"))

        return "Sai email hoặc mật khẩu"

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Kiểm tra email đã tồn tại chưa
        sql_check = """
        SELECT *
        FROM Users
        WHERE email = %s
        """

        cursor.execute(sql_check, (email,))
        user = cursor.fetchone()

        if user:

            cursor.close()
            conn.close()

            return render_template(
                "register.html",
                error="Email đã tồn tại!"
            )

        # Thêm tài khoản mới
        sql_insert = """
        INSERT INTO Users(userName, email, password)
        VALUES (%s, %s, %s)
        """

        cursor.execute(
            sql_insert,
            (username, email, password)
        )

        conn.commit()

        cursor.close()
        conn.close()

        return redirect(url_for("login"))

    return render_template("register.html")


# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/create_group", methods=["GET", "POST"])
def create_group():

    if request.method == "GET":
        return render_template("create_group.html")

    group_name = request.form["groupName"].strip()

    if group_name == "":
        return redirect(url_for("index"))

    userID = session["userID"]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Sinh joinCode không trùng
    while True:

        join_code = ''.join(
            random.choices(
                string.ascii_uppercase + string.digits,
                k=6
            )
        )

        cursor.execute(
            """
            SELECT groupID
            FROM groups
            WHERE joinCode = %s
            """,
            (join_code,)
        )

        if cursor.fetchone() is None:
            break

    # Tạo group
    cursor.execute(
        """
        INSERT INTO groups(
            groupName,
            joinCode,
            createdBy,
            createdAt
        )
        VALUES(%s, %s, %s, NOW())
        """,
        (
            group_name,
            join_code,
            userID
        )
    )

    # Lấy groupID vừa tạo
    groupID = cursor.lastrowid

    # Thêm người tạo vào nhóm và cấp quyền admin
    cursor.execute(
        """
        INSERT INTO groupmembers(
            groupID,
            userID,
            isGroupAdmin,
            joinDate
        )
        VALUES(%s, %s, %s, NOW())
        """,
        (
            groupID,
            userID,
            True
        )
    )

    conn.commit()

    cursor.close()
    conn.close()

    return redirect(url_for("index"))


@app.route("/user", methods=["GET", "POST"])
def userTask():
    if "userID" not in session:
        return redirect(url_for("login"))
    userID = session["userID"]
    sql = """
    select 
        t.*,
        g.groupName,
        g.groupID,
        u.userName as createdByName
    from taskassignments
    join tasks t on taskassignments.taskID = t.taskID
    join groups g on t.groupID = g.groupID
    join users u on t.createdBy = u.userID
    where taskassignments.userID = %s
    order by t.deadline
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql, (userID,))
    tasks = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("user.html", tasks=tasks)



@app.route("/create_task/<int:groupID>", methods=["GET", "POST"])
def addTask(groupID):

    if "userID" not in session:
        return redirect(url_for("login"))
    error = None
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # ======================
    # GET: Hiển thị form
    # ======================
    if request.method == "GET":

        sql = """
        SELECT
            u.userID,
            u.userName
        FROM groupmembers gm
        JOIN users u
            ON gm.userID = u.userID
        WHERE gm.groupID = %s
        """

        cursor.execute(sql, (groupID,))
        members = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            "create_task.html",
            groupID=groupID,
            members=members
        )

    # ======================
    # POST: Tạo task
    # ======================

    title = request.form["title"]
    description = request.form["description"]
    taskLevel = request.form["taskLevel"]
    startDate = request.form["startDate"]
    deadline = request.form["deadline"]

    if title.strip() == "":
        error = "Tiêu đề không được để trống"
        cursor.close()
        conn.close()
        return render_template("create_task.html", groupID=groupID, error=error)
    if startDate > deadline:
        error = "Ngày bắt đầu phải trước hạn chót"
        cursor.close()
        conn.close()
        return render_template("create_task.html", groupID=groupID, error=error)
    if description.strip() == "":
        error = "Mô tả không được để trống"
        cursor.close()
        conn.close()
        return render_template("create_task.html", groupID=groupID, error=error)
    if startDate.strip() == "" or deadline.strip() == "":
        error = "Ngày bắt đầu hoặc hạn chót không được để trống"
        cursor.close()
        conn.close()
        return render_template("create_task.html", groupID=groupID, error=error)
    assignedUsers = request.form.getlist("assignedUsers")
    # Không chọn ai
    if len(assignedUsers) == 0:
        error = "Vui lòng chọn ít nhất một người nhận task"
        cursor.close()
        conn.close()
        return render_template("create_task.html", groupID=groupID, error=error)

    # Nếu chọn ALL MEMBERS
    if "ALL" in assignedUsers:

        cursor.execute("""
            SELECT userID
            FROM groupmembers
            WHERE groupID = %s
        """, (groupID,))

        assignedUsers = [
            str(row["userID"])
            for row in cursor.fetchall()
        ]

    # Tạo task
    sqlTask = """
    INSERT INTO tasks(
        groupID,
        createdBy,
        title,
        description,
        taskLevel,
        taskStatus,
        startDate,
        deadline,
        createdAt
    )
    VALUES(
        %s,
        %s,
        %s,
        %s,
        %s,
        'TODO',
        %s,
        %s,
        NOW()
    )
    """

    cursor.execute(
        sqlTask,
        (
            groupID,
            session["userID"],
            title,
            description,
            taskLevel,
            startDate,
            deadline
        )
    )

    # Lấy taskID vừa tạo
    taskID = cursor.lastrowid

    # Giao task cho từng người
    sqlAssign = """
    INSERT INTO taskassignments(
        taskID,
        userID,
        assignedAt
    )
    VALUES(
        %s,
        %s,
        NOW()
    )
    """

    for userID in assignedUsers:

        cursor.execute(
            sqlAssign,
            (
                taskID,
                userID
            )
        )

    conn.commit()

    cursor.close()
    conn.close()

    return redirect(
        url_for(
            "index"
        )
    )
@app.route("/group/<int:groupID>")
def insideGroup(groupID):

    if "userID" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Thông tin group
    cursor.execute(
        """
        SELECT *
        FROM groups
        WHERE groupID = %s
        """,
        (groupID,)
    )

    group = cursor.fetchone()

    cursor.execute(
        """
        SELECT 
            gm.groupID,
            g.groupName,  
            gm2.userID, 
            gm.userID as idAdmin, 
            u.userName
        FROM groupmembers AS gm
        JOIN groups g ON g.groupID = gm.groupID
        JOIN groupmembers as gm2 ON gm2.groupID = gm.groupID
        JOIN users u ON gm2.userID = u.userID
        WHERE gm.isGroupAdmin = 1 and gm.groupID = %s ;
        """,
        (groupID,)
    )

    members = cursor.fetchall()

    # Các task trong group
    cursor.execute(
        """
        SELECT *
        FROM tasks
        WHERE groupID = %s
        ORDER BY deadline
        """,
        (groupID,)
    )

    tasks = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "inside_group.html",
        group=group,
        members=members,
        tasks=tasks
    )

@app.route("/changeStatusTask/<int:taskID>/<int:new_status>", methods=["GET", "POST"])
def changeStatusTask(taskID, new_status):
    if "userID" not in session:
        return redirect(url_for("login"))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    # Lấy thông tin task
    cursor.execute(
        """
        SELECT *
        FROM tasks
        WHERE taskID = %s
        """,
        (taskID,)
    )
    task = cursor.fetchone()
    if new_status == 1: # Accept review hoặc next status
        if task["taskStatus"] == "TODO":
            new_status = "IN PROCESS"
        elif task["taskStatus"] == "IN PROCESS":
            new_status = "REVIEW"
        elif task["taskStatus"] == "REVIEW":
            new_status = "DONE"
        else:
            new_status = "DONE"
    elif new_status == 2: # Reject review hoặc ReWork
        if task["taskStatus"] == "REVIEW":
            new_status = "IN PROCESS"
        elif task["taskStatus"] == "DONE":
            new_status = "IN PROCESS"
        else:
            new_status = task["taskStatus"]
    # Cập nhật trạng thái mới cho task
    cursor.execute(
        """
        UPDATE tasks
        SET taskStatus = %s
        WHERE taskID = %s
        """,
        (
            new_status,
            taskID
        )
    )
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for("index"))

@app.route("/make_admin/<int:userID>/<int:groupID>")
def makeAdmin(userID, groupID):

    if "userID" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    sql_upadateAdmin_groupmembers = """
        UPDATE groupmembers
        SET isGroupAdmin = 1
        WHERE groupID = %s
        AND userID = %s
    """
    # Cập nhật quyền admin cho user
    cursor.execute(
        sql_upadateAdmin_groupmembers,
        (
            groupID,
            userID
        )
    )
    sqp_delete_my_admin = """
        UPDATE groupmembers
        SET isGroupAdmin = 0
        WHERE groupID = %s
        AND userID = %s
    """
    # Nếu tự cấp quyền admin cho chính mình thì hạ quyền admin của mình
    cursor.execute(
        sqp_delete_my_admin,
        (
            groupID,
            session["userID"]
        )
    )

    conn.commit()

    cursor.close()
    conn.close()

    return redirect(
        url_for(
            "insideGroup",
            groupID=groupID
        )
    )

@app.route("/kick_member/<int:userID>/<int:groupID>")
def kickMember(userID, groupID):

    if "userID" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    sql_kick_member = """
        DELETE FROM groupmembers
        WHERE groupID = %s
        AND userID = %s
    """
    # Xóa member khỏi nhóm
    cursor.execute(
        sql_kick_member,
        (
            groupID,
            userID
        )
    )
    delete_tasks_of_kicked_member = """
        DELETE ta FROM taskassignments ta
        JOIN tasks t ON ta.taskID = t.taskID
        WHERE ta.userID = %s
    """
    cursor.execute(
        delete_tasks_of_kicked_member,
        (userID,)
    )
    conn.commit()

    cursor.close()
    conn.close()

    return redirect(
        url_for(
            "insideGroup",
            groupID=groupID
        )
    )
@app.route("/delete_task/<int:taskID>")
def deleteTask(taskID):

    if "userID" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        DELETE FROM tasks
        WHERE taskID = %s
        """,
        (taskID,)
    )
    cursor.execute(
        """
        DELETE FROM taskassignments
        WHERE taskID = %s
        """,
        (taskID,)
    )

    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for("index"))

@app.route("/edit_task/<int:taskID>", methods=["GET", "POST"])
def editTask(taskID):

    if "userID" not in session:
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Lấy thông tin task
    cursor.execute("""
        SELECT *
        FROM tasks
        WHERE taskID = %s
    """, (taskID,))

    task = cursor.fetchone()

    if not task:
        cursor.close()
        conn.close()
        return "Task không tồn tại"

    # Lấy danh sách thành viên trong group
    cursor.execute("""
        SELECT
            u.userID,
            u.userName
        FROM groupmembers gm
        JOIN users u
            ON gm.userID = u.userID
        WHERE gm.groupID = %s
    """, (task["groupID"],))

    members = cursor.fetchall()

    # Lấy danh sách người đang được giao task
    cursor.execute("""
        SELECT userID
        FROM taskassignments
        WHERE taskID = %s
    """, (taskID,))

    assigned_users = [
        row["userID"]
        for row in cursor.fetchall()
    ]

    # ======================
    # GET
    # ======================
    if request.method == "GET":

        cursor.close()
        conn.close()

        return render_template(
            "edit_task.html",
            task=task,
            members=members,
            assigned_users=assigned_users
        )

    # ======================
    # POST
    # ======================

    title = request.form["title"]
    description = request.form["description"]
    taskLevel = request.form["taskLevel"]
    startDate = request.form["startDate"]
    deadline = request.form["deadline"]

    assignedUsers = request.form.getlist("assignedUsers")

    # Validate
    if title.strip() == "":
        error = "Tiêu đề không được để trống"

        return render_template(
            "edit_task.html",
            task=task,
            members=members,
            assigned_users=assigned_users,
            error=error
        )

    if description.strip() == "":
        error = "Mô tả không được để trống"

        return render_template(
            "edit_task.html",
            task=task,
            members=members,
            assigned_users=assigned_users,
            error=error
        )

    if startDate == "" or deadline == "":
        error = "Ngày bắt đầu và hạn chót không được để trống"

        return render_template(
            "edit_task.html",
            task=task,
            members=members,
            assigned_users=assigned_users,
            error=error
        )

    if startDate > deadline:
        error = "Ngày bắt đầu phải trước hạn chót"

        return render_template(
            "edit_task.html",
            task=task,
            members=members,
            assigned_users=assigned_users,
            error=error
        )

    if len(assignedUsers) == 0:
        error = "Vui lòng chọn ít nhất một người"

        return render_template(
            "edit_task.html",
            task=task,
            members=members,
            assigned_users=assigned_users,
            error=error
        )

    # Nếu chọn ALL MEMBERS
    if "ALL" in assignedUsers:

        cursor.execute("""
            SELECT userID
            FROM groupmembers
            WHERE groupID = %s
        """, (task["groupID"],))

        assignedUsers = [
            str(row["userID"])
            for row in cursor.fetchall()
        ]

    # Update task
    cursor.execute("""
        UPDATE tasks
        SET
            title = %s,
            description = %s,
            taskLevel = %s,
            startDate = %s,
            deadline = %s
        WHERE taskID = %s
    """, (
        title,
        description,
        taskLevel,
        startDate,
        deadline,
        taskID
    ))

    # Xóa assignment cũ
    cursor.execute("""
        DELETE FROM taskassignments
        WHERE taskID = %s
    """, (taskID,))

    # Thêm assignment mới
    sqlAssign = """
    INSERT INTO taskassignments(
        taskID,
        userID,
        assignedAt
    )
    VALUES(
        %s,
        %s,
        NOW()
    )
    """

    for userID in assignedUsers:

        cursor.execute(
            sqlAssign,
            (
                taskID,
                userID
            )
        )

    conn.commit()

    cursor.close()
    conn.close()

    return redirect(
        url_for(
            "index"
        )
    )

@app.route("/search")
def search():

    if "userID" not in session:
        return redirect(url_for("login"))

    keyword = request.args.get("keyword", "").strip()

    if keyword == "":
        return redirect(url_for("index"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Tìm group
    sqlGroup = """
    SELECT *
    FROM groups
    WHERE groupName LIKE %s
       OR joinCode LIKE %s
    """

    cursor.execute(
        sqlGroup,
        (
            f"%{keyword}%",
            f"%{keyword}%"
        )
    )

    groups = cursor.fetchall()

    # Tìm task
    sqlTask = """
    SELECT
        t.*,
        g.groupName
    FROM tasks t
    JOIN groups g
        ON t.groupID = g.groupID
    WHERE t.title LIKE %s
       OR t.description LIKE %s
    ORDER BY t.deadline
    """

    cursor.execute(
        sqlTask,
        (
            f"%{keyword}%",
            f"%{keyword}%"
        )
    )

    tasks = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "search.html",
        keyword=keyword,
        groups=groups,
        tasks=tasks
    )


@app.route("/join_group/<int:groupID>")
def join(groupID):
    if "userID" not in session:
        return redirect(url_for("login"))

    userID = session["userID"]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Kiểm tra đã tham gia chưa
    cursor.execute(
        """
        SELECT *
        FROM groupmembers
        WHERE groupID = %s
        AND userID = %s
        """,
        (groupID, userID)
    )

    member = cursor.fetchone()

    if member:
        cursor.close()
        conn.close()

        return redirect(
            url_for(
                "group",
                groupID=groupID
            )
        )

    # Thêm vào nhóm
    cursor.execute(
        """
        INSERT INTO groupmembers(
            groupID,
            userID,
            isGroupAdmin,
            joinDate
        )
        VALUES(
            %s,
            %s,
            0,
            NOW()
        )
        """,
        (
            groupID,
            userID
        )
    )

    conn.commit()

    cursor.close()
    conn.close()

    return redirect(
        url_for(
            "index"
        )
    )


if __name__ == "__main__":
    app.run(debug=True)