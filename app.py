from flask import Flask, render_template, request, redirect, url_for, session,jsonify
from flask_wtf.csrf import CSRFProtect, generate_csrf
import pyodbc
import os
import logging
import math

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.urandom(24)  # Generate and set the secret key

def get_db_connection():
    return pyodbc.connect('DRIVER={SQL Server};SERVER=192.168.100.115,1433;DATABASE=DashboardDB;UID=Admin@3;PWD=Admin@3;')

PER_PAGE = 7

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    role = request.form['role']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, Password, Role FROM Users WHERE Username = ?', (username,))
    user = cursor.fetchone()
    if user and user[1] == password and user[2] == role:
        session['user_id'] = user[0]
        if role == 'employee':
            return redirect(url_for('dashboard_employee'))
        elif role == 'manager':
            return redirect(url_for('dashboard_manager'))
        elif role == 'administrator':
            return redirect(url_for('dashboard_administrator'))
    else:
        return render_template('login.html', error='Invalid username, password, or role')

@app.route('/dashboard_employee')
def dashboard_employee():
    # Ensure user_id is available in the session
    if 'user_id' not in session:
        return "User not authenticated", 401
    
    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch employee's name
        cursor.execute('SELECT Username FROM Users WHERE id = ?', (user_id,))
        employee = cursor.fetchone()
        employee_name = employee[0] if employee else "Employee not found"

        # Fetch manager's name
        cursor.execute('''
            SELECT u_manager.name AS manager_name
            FROM Users u_user
            JOIN Teams t ON u_user.team_id = t.team_id
            JOIN Users u_manager ON t.manager_id = u_manager.id
            WHERE u_user.id = ? 
        ''', (user_id,))
        manager = cursor.fetchone()
        manager_name = manager[0] if manager else "Manager not found"

        # Fetch work details for the employee
        cursor.execute('''
            SELECT id, project_name, project_status, team_id, deadline
            FROM Projects
            WHERE team_id = (
                SELECT team_id
                FROM Users
                WHERE id = ?
            )
        ''', (user_id,))
        work_details = cursor.fetchall()

        # Fetch team members' names
        cursor.execute('''
            SELECT id, name, contactnumber, email
            FROM Users
            WHERE team_id = (
                SELECT team_id
                FROM Users
                WHERE id = ?
            ) AND role = 'Employee' AND id != ?
        ''', (user_id, user_id))
        team_members = cursor.fetchall()

        # Fetch projects categorized by status
        cursor.execute('''
            SELECT id, project_name, project_status, team_id, deadline
            FROM Projects
            WHERE team_id = (
                SELECT team_id
                FROM Users
                WHERE id = ?
            )
        ''', (user_id,))
        projects = cursor.fetchall()

        completed_projects = []
        in_progress_projects = []
        waiting_projects = []

        for project in projects:
            if project[2] in ['Planning', 'Design']:
                completed_projects.append(project)
            elif project[2] == 'Development':
                in_progress_projects.append(project)
            elif project[2] == 'Testing':
                waiting_projects.append(project)

        cursor.close()
        conn.close()

        return render_template('dashboard_employee.html',
                               employee_name=employee_name,
                               manager_name=manager_name,
                               completed_projects=completed_projects,
                               in_progress_projects=in_progress_projects,
                               waiting_projects=waiting_projects,
                               work_details=work_details,
                               team_members=team_members)

    except Exception as e:
        return f"An error occurred: {str(e)}", 500

@app.route('/assign_manager', methods=['GET', 'POST'])
def assign_manager():
  form = AssignManagerForm()
  # Get manager data
  managers = get_managers_from_database()  # Replace with your logic

  # Filter employees by role "employee"
  connection = get_database_connection()
  cursor = connection.cursor()
  cursor.execute("SELECT username, role, name, manager_id FROM Users WHERE role = 'employee'")
  employee_data = cursor.fetchall()
  connection.close()

  # Prepare employee data for template
  employees = []
  for row in employee_data:
    employees.append({
      'username': row[0],
      'role': row[1],
      'name': row[2],
      'manager_id': row[3],  # Assuming you have a manager_id field
    })

  return render_template('assigning_manager.html', form=form, managers=managers, employees=employees)
@app.route('/update_manager', methods=['POST'])
def update_manager():
    try:
        # Get form data from request
        team_id = request.form.get('team_id')
        manager_id = request.form.get('manager_id')

        # Update manager_id in teams table
        conn = get_db_connection()
        
        # Using context manager for cursor
        with conn.cursor() as cursor:
            cursor.execute('UPDATE teams SET manager_id = ? WHERE team_id = ?', (manager_id, team_id))
            conn.commit()

            return jsonify({'message': 'Manager updated successfully'}), 200

    except pyodbc.Error as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Ensure connection closure in case of any exception or successful execution
        if 'conn' in locals():
            conn.close()

@app.route('/fetch_managers', methods=['GET'])
def fetch_managers():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM Users WHERE Role = ?', ('manager',))
    managers = [{'id': row.id, 'name': row.name} for row in cursor.fetchall()]
    conn.close()
    return jsonify({'managers': managers})


@app.route('/managers', methods=['GET'])
def get_managers():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Query to select users with role 'manager'
        cursor.execute("SELECT id, username FROM Users WHERE role = 'manager'")
        managers = cursor.fetchall()

        # Close cursor and connection
        cursor.close()
        conn.close()

        # Convert managers to a list of dictionaries
        managers_list = [{'id': manager.id, 'name': manager.username} for manager in managers]
        
        return jsonify(managers_list)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/manage-teams')
def manage_teams():
    try:
        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Execute query to fetch teams
        cursor.execute('''
            SELECT t.team_id, t.team_name, u.name as manager_name 
            FROM teams t
            LEFT JOIN users u ON t.manager_id = u.id
        ''')
        # Fetch all teams
        teams = cursor.fetchall()

        # Close cursor and connection
        cursor.close()
        conn.close()

        # Render template with teams data
        return render_template('manage-teams.html', teams=teams)

    except Exception as e:
        return f"An error occurred: {str(e)}"

@app.route('/delete_team/<int:team_id>', methods=['DELETE'])
def delete_team(team_id):
    try:
        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Execute query to delete team
        cursor.execute('DELETE FROM teams WHERE team_id = ?', (team_id,))
        
        # Check if any rows were affected
        if cursor.rowcount == 0:
            # No team with the specified ID found
            conn.rollback()  # Rollback the transaction
            return jsonify({'error': 'Team not found'}), 404
        
        # Commit the transaction
        conn.commit()

        # Close cursor and connection
        cursor.close()
        conn.close()

        # Return success message
        return jsonify({'message': 'Team deleted successfully'}), 200

    except pyodbc.Error as e:
        # Log database error
        app.logger.error(f'Database error occurred: {str(e)}')
        return jsonify({'error': 'Database error occurred'}), 500

    except Exception as e:
        # Log unexpected error
        app.logger.error(f'Unexpected error occurred: {str(e)}')
        return jsonify({'error': 'An unexpected error occurred'}), 500

@app.route('/add-team', methods=['POST'])
def add_team():
    try:
        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Retrieve team name from form data
        team_name = request.form['team_name']

        # Insert into database
        cursor.execute('INSERT INTO teams (team_name) VALUES (?)', (team_name,))
        conn.commit()

        # Return success message
        return jsonify({'message': 'Team added successfully'}), 200

    except pyodbc.Error as e:
        # Log database error
        app.logger.error(f'Database error occurred: {str(e)}')
        return jsonify({'error': 'Database error occurred'}), 500

    except Exception as e:
        # Log unexpected error
        app.logger.error(f'Unexpected error occurred: {str(e)}')
        return jsonify({'error': 'An unexpected error occurred'}), 500

@app.route('/manage-projects')
def manage_projects():
    projects = fetch_projects_from_db()
    teams = fetch_teams_from_db()
    return render_template('manage-projects.html', projects=projects, teams=teams)

# Function to fetch project names from database
def fetch_projects_from_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, project_name, project_status, team_id, deadline FROM Projects')
        projects = cursor.fetchall()
        cursor.close()
        conn.close()
        return projects
    except pyodbc.Error as e:
        print(f"Error fetching projects: {e}")
        return []
def fetch_teams_from_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT team_id, team_name FROM Teams')
        teams = cursor.fetchall()
        
        # Convert pyodbc.Row objects to dictionaries
        team_list = [{'id': team.team_id, 'team_name': team.team_name} for team in teams]
        
        cursor.close()
        conn.close()
        
        return team_list  # Return a list of dictionaries
    except pyodbc.Error as e:
        print(f"Error fetching teams: {e}")
        return []

@app.route('/add-project', methods=['GET', 'POST'])
def add_project():
    if request.method == 'POST':
        project_name = request.form['project_name']
        project_status = request.form['project_status']
        team_id = request.form['team_id']
        deadline = request.form['deadline']

        # Insert into database
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('INSERT INTO Projects (project_name, project_status, team_id, deadline) VALUES (?, ?, ?, ?)',
                           (project_name, project_status, team_id, deadline))
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('manage_projects'))
        except pyodbc.Error as e:
            print(f"Error adding project: {e}")
            return "Error adding project"
    else:
        return redirect(url_for('manage_projects'))

@app.route('/delete-project/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    if request.method == 'DELETE':
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Execute the delete query
            cursor.execute('DELETE FROM Projects WHERE id = ?', (project_id,))
            conn.commit()

            cursor.close()
            conn.close()

            return 'Project deleted successfully!', 200  # Respond with success message
        except pyodbc.Error as e:
            print(f"Error deleting project: {e}")
            return 'Error deleting project', 500  # Respond with error message
    else:
        return 'Method not allowed', 405  # Respond with method not allowed error

@app.route('/dashboard_manager', methods=['GET', 'POST'])
def dashboard_manager():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch manager's name
        cursor.execute('SELECT Username FROM Users WHERE id = ?', (user_id,))
        manager_result = cursor.fetchone()
        if manager_result:
            manager_name = manager_result[0]
        else:
            manager_name = "Unknown Manager"

        # Fetch teams managed by the manager with their project details and team members
        cursor.execute('''
            SELECT u.id, u.name, u.contactnumber, u.email
            FROM Users u
            JOIN Teams t ON u.team_id = t.team_id
            WHERE t.manager_id = ?
        ''', (session['user_id'],))
        team_members = cursor.fetchall()

        cursor.execute('''
            SELECT p.id, p.project_name, p.project_status, p.team_id, p.deadline
            FROM Projects p
            JOIN Teams t ON p.team_id = t.team_id
            WHERE t.manager_id = ?
        ''', (session['user_id'],))
        work_details = cursor.fetchall()

        conn.close()

        return render_template('dashboard_manager.html', work_details=work_details, team_members=team_members, manager_name=manager_name)

    elif request.method == 'POST':
        # Handle project status update
        project_id = request.form['project_id']
        new_status = request.form['new_status']

        conn = get_db_connection()
        cursor = conn.cursor()

        # Update the project status in the database
        cursor.execute('UPDATE Projects SET project_status = ? WHERE id = ?', (new_status, project_id))
        conn.commit()
        conn.close()

        # Optionally, you can redirect to a success page or render a message in the dashboard
        return redirect(url_for('dashboard_manager'))

@app.route('/update_project_status', methods=['POST'])
def update_project_status():
    project_id = request.form['project_id']
    new_status = request.form['new_status']
    print(f"Received POST request: project_id={project_id}, new_status={new_status}")
    

    # Update project status in the database (replace with your database logic)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE Projects SET project_status = ? WHERE id = ?', (new_status, project_id))
    conn.commit()

    # Fetch updated data (if needed) after update
    cursor.execute('SELECT * FROM Projects WHERE id = ?', (project_id,))
    updated_project = cursor.fetchone()

    conn.close()

    # Check if updated_project is valid
    if updated_project:
        # Access columns using integer indices (0-based)
        updated_project_dict = {
            'id': updated_project[0],
            'project_name': updated_project[1],
            'project_status': updated_project[2],
            'team_id': updated_project[3],
            'deadline': updated_project[4]
            # Add other fields as needed
        }

        # Return updated data and success message as JSON
        return jsonify({
            'message': 'Project status updated successfully',
            'updated_project': updated_project_dict
        })
    else:
        return jsonify({
            'error': 'Project not found or update failed'
        }), 404

# Route to fetch all team names
@app.route('/get_team_data', methods=['GET'])
def get_team_data():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Execute query to fetch team names
        cursor.execute('SELECT team_id, team_name FROM Teams')  # Adjust table and column names as per your database schema
        teams = cursor.fetchall()

        # Format the data into JSON
        team_data = [{'id': team[0], 'name': team[1]} for team in teams]
        print(team_data)

        return jsonify({'teams': team_data})
    except Exception as e:
        # Handle exceptions appropriately (e.g., log the error, return an error response)
        print(f"Error fetching team data: {str(e)}")
        return jsonify({'error': 'Failed to fetch team data'})

    finally:
        # Close cursor and connection
        cursor.close()
        conn.close()


@app.route('/update_employee', methods=['POST'])
def update_employee():
    print("Received POST request data:")
    print(request.form)

    # Get form data from request
    username = request.form['username']
    role = request.form['role']
    name = request.form['name']
    email = request.form['email']
    contact = request.form['contact']
    team_id = request.form['team']  # Assuming team ID is sent from form
    
    # Convert "NULL" string to None for team_id

    print("team_id:", team_id)

    # Perform update in your database
    # Example SQL update query (adjust as per your database schema)
    conn = get_db_connection()  # Implement your database connection function
    cursor = conn.cursor()
    
    # Example update query (adjust according to your schema)
    cursor.execute("""
        UPDATE Users
        SET Role = ?, name = ?, email = ?, contactnumber = ?, team_id = ?
        WHERE username = ?
    """, (role, name, email, contact, team_id, username))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Employee updated successfully'})


@app.route('/get_employee_details', methods=['GET'])
def get_employee_details():
    username = request.args.get('username')
    if not username:
        return jsonify({'error': 'No username provided'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT 
        u_user.username,
        u_user.name,
        u_user.email,
        u_user.contactnumber AS contact,
        t.team_name,
        u_manager.name AS manager_name
    FROM Users u_user
    JOIN Teams t ON u_user.team_id = t.team_id
    JOIN Users u_manager ON t.manager_id = u_manager.id
    WHERE u_user.username = ?
    """
    cursor.execute(query, (username,))
    row = cursor.fetchone()
    conn.close()

    if row:
        employee = {
            'username': row.username,
            'name': row.name,
            'email': row.email,
            'contact': row.contact,
            'manager_name': row.manager_name,
            'team_name' : row.team_name
        }
        return jsonify(employee)
    else:
        return jsonify({'error': 'Employee not found'}), 404

@app.route('/dashboard_administrator', methods=['GET', 'POST'])
def dashboard_administrator():
    conn = get_db_connection()
    cursor = conn.cursor()
    manage_employee_offset = 0
    active_tab = request.args.get('active_tab', 'add-employee')
    manage_employee_page = int(request.args.get('manage_employee_page', 1))
    selected_role = request.args.get('role', 'all')
    if selected_role == 'all':
        cursor.execute('SELECT Username, Role, name FROM Users ORDER BY Username OFFSET ? ROWS FETCH NEXT ? ROWS ONLY', (manage_employee_offset, PER_PAGE))
    else:
        cursor.execute('SELECT Username, Role, name, email, contactnumber AS contact FROM Users WHERE Role = ? ORDER BY Username OFFSET ? ROWS FETCH NEXT ? ROWS ONLY', (selected_role, manage_employee_offset, PER_PAGE))
    
    manage_employee_users = cursor.fetchall()
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        name = request.form['name']
        email = request.form['email']
        contact = request.form['contact']

        cursor.execute(
            'INSERT INTO Users (Password, Role, name, email, contactnumber) VALUES ( ?, ?, ?, ?, ?)',
            (password, role, name, email, contact) 
        )
        conn.commit()
        if 'delete-username' in request.form:
            username_to_delete = request.form['delete-username']
            cursor.execute('DELETE FROM Users WHERE Username = ?', (username_to_delete,))
            conn.commit()
            return redirect(url_for('dashboard_administrator'))
        return redirect(url_for('dashboard_administrator'))

    if 'view-username' in request.args:
        username = request.args.get('view-username')
        cursor.execute('SELECT Role, name, email, contactnumber, managerid FROM Users WHERE Username = ?', (username,))
        employee_data = cursor.fetchone()
        if employee_data:
            role, name, email, contact, managerid = employee_data
            cursor.execute('SELECT name FROM Users WHERE id = ?', (managerid,))
            manager_data = cursor.fetchone()
            manager_name = manager_data[0] if manager_data else 'N/A'
            return jsonify({
                'role': role,
                'name': name,
                'email': email,
                'contact': contact,
                'manager': manager_name
            })

        

    # Get the page number for each tab from the query string, default to 1
    add_employee_page = request.args.get('add_employee_page', 1, type=int)
    manage_employee_page = request.args.get('manage_employee_page', 1, type=int)  # Ensure manage_employee_page is defined
    manage_projects_page = request.args.get('manage_projects_page', 1, type=int)
    active_tab = request.args.get('tab', 'add-employee')
    if active_tab == 'add-employee':
        page_key = 'add_employee_page'
    elif active_tab == 'manage-employees':
        page_key = 'manage_employee_page'
    elif active_tab == 'manage-projects':
        page_key = 'manage_projects_page'
    else:
        page_key = 'add_employee_page'

    # Get the total number of records for each tab
    cursor.execute('SELECT COUNT(*) FROM Users')
    total_records = cursor.fetchone()[0]

    # Calculate the total number of pages for each tab
    total_pages_add_employee = math.ceil(total_records / PER_PAGE)
    total_pages_manage_employee = math.ceil(total_records / PER_PAGE)
    total_pages_manage_projects = math.ceil(total_records / PER_PAGE)

    # Calculate the offset for the SQL query for each tab
    add_employee_offset = (add_employee_page - 1) * PER_PAGE
    manage_employee_offset = (manage_employee_page - 1) * PER_PAGE
    manage_projects_offset = (manage_projects_page - 1) * PER_PAGE

    # Fetch the records for the current page for each tab
    cursor.execute('SELECT Username, Role, name FROM Users ORDER BY Username OFFSET ? ROWS FETCH NEXT ? ROWS ONLY', (add_employee_offset, PER_PAGE))
    add_employee_users = cursor.fetchall()

    cursor.execute('SELECT Username, Role, name, email, contactnumber FROM Users ORDER BY Username OFFSET ? ROWS FETCH NEXT ? ROWS ONLY', (manage_employee_offset, PER_PAGE))
    manage_employee_users = cursor.fetchall()

    cursor.execute('SELECT Username, Role, name FROM Users ORDER BY Username OFFSET ? ROWS FETCH NEXT ? ROWS ONLY', (manage_projects_offset, PER_PAGE))
    manage_projects_users = cursor.fetchall()

    # Calculate URLs for next and previous pages for each tab
    add_employee_prev_url = url_for('dashboard_administrator', active_tab='add-employee', add_employee_page=add_employee_page-1) if add_employee_page > 1 else None
    add_employee_next_url = url_for('dashboard_administrator', active_tab='add-employee', add_employee_page=add_employee_page+1) if add_employee_page < total_pages_add_employee else None

    manage_employee_total_pages = math.ceil(total_records / PER_PAGE)
    manage_employee_prev_url = url_for('dashboard_administrator', active_tab='manage-employees', manage_employee_page=manage_employee_page-1) if manage_employee_page > 1 else None
    manage_employee_next_url = url_for('dashboard_administrator', active_tab='manage-employees', manage_employee_page=manage_employee_page+1) if manage_employee_page < manage_employee_total_pages else None

    manage_projects_prev_url = url_for('dashboard_administrator', active_tab='manage-projects', manage_projects_page=manage_projects_page-1) if manage_projects_page > 1 else None
    manage_projects_next_url = url_for('dashboard_administrator', active_tab='manage-projects', manage_projects_page=manage_projects_page+1) if manage_projects_page < total_pages_manage_projects else None

    cursor.close()
    conn.close()

    return render_template('dashboard_administrator.html',
                           add_employee_users=add_employee_users,
                           manage_employee_users=manage_employee_users,
                           manage_projects_users=manage_projects_users,
                           add_employee_prev_url=add_employee_prev_url,
                           add_employee_next_url=add_employee_next_url,
                           manage_employee_prev_url=manage_employee_prev_url,
                           manage_employee_next_url=manage_employee_next_url,
                           manage_projects_prev_url=manage_projects_prev_url,
                           manage_projects_next_url=manage_projects_next_url,
                           add_employee_current_page=add_employee_page,
                           add_employee_total_pages=total_pages_add_employee,
                           manage_employee_current_page=manage_employee_page,  # Pass manage_employee_page here
                           manage_employee_total_pages=total_pages_manage_employee,
                           manage_projects_current_page=manage_projects_page,
                           manage_projects_total_pages=total_pages_manage_projects,
                           selected_role=selected_role,
                           active_tab=active_tab, manage_employee_page=manage_employee_page)


@app.route('/add_employee', methods=['POST'])
def add_employee():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        name = request.form['name']
        email = request.form['email']
        contact = request.form['contact']
        role = request.form['role']
        print(f"Received POST request data: username={username}, password={password}, "
              f"role={role}, name={name}, "
              f"contact_number={contact}, email={email}")
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO Users (username, password, name, email, contactnumber, role) VALUES (?, ?, ?, ?, ?, ?)", (username, password, name, email, contact, role))
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('dashboard_administrator', active_tab='manage-employees'))
        except pyodbc.Error as e:
            print(f"Error adding employee: {e}")
            return redirect(url_for('dashboard_administrator', active_tab='manage-employees'))
# Route to handle password change
@app.route('/change_password', methods=['POST'])
def change_password():
    # Get database connection
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if 'user_id' not in session:
            return redirect(url_for('login'))  # Redirect if user is not logged in

        # Print the request received for debugging
        print("Form Data:", request.form)

        new_password = request.form.get('new_password')

        if not new_password:
            return "New password not provided", 400

        user_id = session['user_id']

        # SQL query to update password
        cursor.execute('UPDATE Users SET password = ? WHERE id = ?;', (new_password, user_id))
        conn.commit()  # Commit the transaction

        return "Password changed successfully"

    except Exception as e:
        return f"Failed to change password: {str(e)}", 500

    finally:
        cursor.close()
        conn.close()

@app.route('/delete_employee', methods=['POST'])
def delete_employee():
    conn = get_db_connection()
    cursor = conn.cursor()
    username_to_delete = request.form['username']
    cursor.execute('DELETE FROM Users WHERE Username = ?', (username_to_delete,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('dashboard_administrator'))



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        role = request.form['role']
        name = request.form['name']
        contact_number = request.form['contact_number']
        email = request.form['email']

        if password != confirm_password:
            return render_template('register.html', error='Passwords do not match')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(1) FROM Users WHERE Username = ?', (username,))
        count = cursor.fetchone()[0]
        if count > 0:
            cursor.close()
            conn.close()
            return render_template('register.html', error='Username already exists')

        cursor.execute(
            'INSERT INTO Users (Username, Password, Role, Name, ContactNumber, Email) VALUES (?, ?, ?, ?, ?, ?)',
            (username, password, role, name, contact_number, email)
        )
        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('index'))

    return render_template('register.html')

@app.route('/success')
def success():
    return 'Login successful!'

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)