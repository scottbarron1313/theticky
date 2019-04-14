#Need to use gc.collect() to garbage collection the connection (may help with problems)
#Close your connections

import psycopg2
import sys
import os
import getpass
from flask import Flask, render_template, request, Markup, current_app, Response, redirect, url_for, session, g
from flask_login import LoginManager, login_required, login_user, UserMixin, current_user
from wtforms import Form
#Use this to encrypt passwords
from passlib.hash import sha256_crypt 
#Use this to deal with SQL injection
# from MySQLdb import escape_string as thwart
import gc
import requests
from requests.exceptions import RequestException
from contextlib import closing
from bs4 import BeautifulSoup

from functools import wraps
import argparse
from functools import wraps
from urllib.parse import urlparse
import smtplib
from email.mime.text import MIMEText
import json
import time
import re


# ------------------------------------------------------
#Extra Functions

def dm2dd(degrees, minutes, direction):
    dd = float(degrees) + float(minutes)/60
    if direction == 's' or direction == 'w':
        dd *= -1
    return dd


#Web scraping

def simple_get(url):
    """
    Attempts to get the content at `url` by making an HTTP GET request.
    If the content-type of response is some kind of HTML/XML, return the
    text content, otherwise return None.
    """
    try:
        with closing(requests.get(url, stream=True, headers = {'User-Agent' : 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.143 Safari/537.36'})) as resp:
            if is_good_response(resp):
                return resp.content
            else:
                return None

    except RequestException as e:
        log_error('Error during requests to {0} : {1}'.format(url, str(e)))
        return None


def is_good_response(resp):
    """
    Returns True if the response seems to be HTML, False otherwise.
    """
    content_type = resp.headers['Content-Type'].lower()
    return (resp.status_code == 200 
            and content_type is not None 
            and content_type.find('html') > -1)


def log_error(e):
    """
    It is always a good idea to log errors. 
    This function just prints them, but you can
    make it do anything.
    """
    print(e)

def v_to_font_boulder(v_grade):
    v_font_boulder_conversion = {17:'9a', 
                                    16:'8c+',
                                    15:'8c', 
                                    14:'8b+', 
                                    13:'8b', 
                                    12:'8a+', 
                                    11:'8a', 
                                    10:'7c+', 
                                    9:'7c', 
                                    8:'7b+', 
                                    7:'7a+', 
                                    6:'7a', 
                                    5:'6c+',
                                    4:'6b',
                                    3:'6a+',
                                    2:'5c',
                                    1:'5b',
                                    0:'5a'}

    font_grade = v_font_boulder_conversion[int(v_grade)]
    return font_grade

def font_to_v_boulder(font_grade):
    font_v_boulder_conversion = {'9a':17, 
                                    '8c+':16,
                                    '8c':15, 
                                    '8b+':14, 
                                    '8b':13, 
                                    '8a+':12, 
                                    '8a':11, 
                                    '7c+':10, 
                                    '7c':9, 
                                    '7b+':8, 
                                    '7b':8,
                                    '7a+':7, 
                                    '7a':6, 
                                    '6c+':5,
                                    '6c':5,
                                    '6b+':4,
                                    '6b':4,
                                    '6a+':3,
                                    '6a':3,
                                    '5c+':2,
                                    '5c':2,
                                    '5b+':1,
                                    '5b':1,
                                    '5a+':0,
                                    '5a':0,
                                    '3a':0}

    v_grade = font_v_boulder_conversion[font_grade.lower()]
    return v_grade



# ------------------------------------------------------
#Login required decorator
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            return redirect(url_for('login'))
    return wrap

#To Hash a password, sha256_crypt.encrypt(str(password))

app = Flask(__name__)
app.secret_key= os.urandom(24)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

url = urlparse(os.environ['DATABASE_URL'])

#logout page
@app.route('/logout')
def logout():
    session.clear()
    gc.collect()
    return redirect(url_for('login'))

#Login page
@app.route("/login", methods = ["GET", "POST"])
def login():
    #Need to do this to run on local:
    #export DATABASE_URL=postgres://opimlbnkhudqpv:e2c778406ab743a2bcdef8ce2c07544ba66dc50a75c241e4929215b1b2198f83@ec2-107-21-108-204.compute-1.amazonaws.com:5432/df9g9j9vm0bu32
    url = urlparse(os.environ['DATABASE_URL'])

    error = None
    success = None

    if request.method == 'POST':
        session.pop('user', None)

        #Connect to database on heroku
        login_conn= psycopg2.connect(database=url.path[1:],
                                    user=url.username,
                                    password=url.password,
                                    host=url.hostname,
                                    port=url.port)

        login_conn.autocommit= True
        login_cur = login_conn.cursor()

        #Main login fucntion here
        if 'password' in request.form:
            #Check password
            login_cur.execute("SELECT id, password FROM users WHERE username = %s;", (request.form['username'],))
            
            response = login_cur.fetchall()

            if len(response)== 0:
                error = 'Incorrect Username/Password'
            else:
                if sha256_crypt.verify(request.form['password'], response[0][1])== True:
                    session['logged_in'] = True
                    session['user'] = request.form['username']
                    login_cur.close()
                    login_conn.close()
                    gc.collect()
                    return redirect(url_for('ticklist', user = '{a}_{b}'.format(a = session['user'], 
                                                                                b = response[0][0])))

                else:
                    error = 'Incorrect Username/Password'

        #Creates a new user
        elif 'new_username' in request.form:
            new_username = request.form['new_username']
            if ' ' in new_username:
                error = 'Please enter a username without spaces'
                return render_template('login_new.html', error = error)

            new_password = sha256_crypt.encrypt(str(request.form['new_password']))
            new_email = request.form['new_email']

            #Create new account
            login_cur.execute("SELECT username FROM users where username = %s;", (new_username,))
            existing_username = login_cur.fetchall()
            login_cur.execute("SELECT email FROM users where email = %s;", (new_email,))
            existing_email = login_cur.fetchall()

            if len(existing_username)!= 0 or len(existing_email)!= 0:
                error = 'Account already exists!'
                return render_template('login_new.html', error = error)

            login_cur.execute("INSERT INTO users (username, password, email, firstname, lastname, dob, height, weight) VALUES (%s, %s, %s, %s, %s, %s, %i, %i);", (new_username, 
                                                                                                                                                                    new_password, 
                                                                                                                                                                    new_email, 
                                                                                                                                                                    request.form['new_firstname'], 
                                                                                                                                                                    request.form['new_lastname'], 
                                                                                                                                                                    request.form['new_dob'], 
                                                                                                                                                                    request.form['new_height'], 
                                                                                                                                                                    request.form['new_weight']))
            new_success = 'Account Created!'
            return render_template('login_new.html', new_success = new_success)

        #Forgot login section
        #Still needs work
        elif 'email_password' in request.form:
            #If the user forgets their login, email them their password
            recovery_msg= MIMEText('Testy test')
            recovery_msg['Subject']= 'Ticky Login Recovery'
            recovery_msg['From']= 'scottbarron13@gmail.com'
            recovery_msg['To']= request.form['request_login']

            s = smtplib.SMTP('localhost')
            s.sendmail('scottbarron13@gmail.com', [request.form['request_login']], recovery_msg.as_string())
            s.quit()

        #Catch all for any other scenario
        else:
            print('OTHER')
            print(request.form)

    return render_template('login_new.html', error= error, success= success)

# Main page
@app.route("/", methods=["GET", "POST"])
#Comment in to require password
@login_required
def home():
    # # get a connection, if a connect cannot be made an exception will be raised here
    # url = urlparse.urlparse(os.environ['DATABASE_URL'])
    # conn= psycopg2.connect(database=url.path[1:],
    #                         user=url.username,
    #                         password=url.password,
    #                         host=url.hostname,
    #                         port=url.port)

    # conn.autocommit = True

    # # conn.cur will return a cur object, you can use this cur to perform queries
    # cur = conn.cursor()

    return redirect(url_for('ticklist', user = '{a}_{b}'.format(a = session['user'],
                                                                    b = response[0][0])))


#Ticklist page
@app.route("/ticklist/<user>", methods = ["GET"])
@login_required
def ticklist(user):
    # get a connection, if a connect cannot be made an exception will be raised here
    url = urlparse(os.environ['DATABASE_URL'])
    conn = psycopg2.connect(database=url.path[1:],
                            user=url.username,
                            password=url.password,
                            host=url.hostname,
                            port=url.port)

    conn.autocommit = True

    current_user = session['user']
    user_id = user.split('_')[-1]

    # conn.cur will return a cur object, you can use this cur to perform queries
    cur = conn.cursor()

    #------------------------------------------
    #User info
    cur.execute("SELECT firstname, lastname, dob, height, weight FROM users WHERE id = {};".format(user_id))
    info = cur.fetchall()[0]
    firstname = info[0]
    lastname = info[1]
    dob = info[2]
    height = info[3]
    weight = info[4]

    #------------------------------------------
    cur.execute('SELECT climbs.id as cid, ticks.log_date, climbs.name as climb, sectors.name as sector, sectors.crag_name, ticks.suggested_grade, ticks.comment FROM ticks INNER JOIN users ON ticks.user_id = users.id INNER JOIN climbs ON ticks.climb_id = climbs.id INNER JOIN sectors ON climbs.sector_id = sectors.id WHERE users.id = {} ORDER BY ticks.log_date DESC;'.format(user_id))

    ticks = cur.fetchall()

    #------------------------------------------
    #Ticklist table creation
    ticklist_columns = [desc[0] for desc in cur.description]

    table= '<thead class= "thead-dark"><tr>'
    for header in ticklist_columns:
        if header != 'cid':
            table += '<th>{header}</th>'.format(header= header.replace('_',' ').title())

    table += '</tr></thead><tbody>'

    for row in ticks:
        table += '<tr>'
        for num, item in enumerate(row):
            if item == None:
                item = 'n/a'

            if num == ticklist_columns.index('suggested_grade'):
                table += '<td>V{a}</td>'.format(a = item)
            elif num == ticklist_columns.index('log_date'):
                table += '<td>{a}</td>'.format(a = item)
            elif num == ticklist_columns.index('cid'):
                cid = item
            elif num == ticklist_columns.index('climb'):
                table += '<td><a href= "/climb/{a}">{b}</a></td>'.format(a = cid,
                                                                        b = item.replace('&apos&',"'").replace('&amp;',"'").title().replace("'S", "'s"))
            elif num == ticklist_columns.index('comment'):
                table += '<td>{a}</td>'.format(a = item.replace('&apos&',"'"))
            elif num == ticklist_columns.index('crag_name'):
                table += '<td>{a}</td>'.format(a = item.replace('&apos&',"'").title().replace("'S", "'s"))
            else:
                table += '<td>{a}</td>'.format(a = item.title())
        table += '</tr>'

    table += '</tbody></body>'
    #------------------------------------------

    return render_template("ticklist_template.html", username = current_user,
                                                     main_page = Markup(table),
                                                     fname = firstname,
                                                     lname = lastname,
                                                     dob = dob,
                                                     height = height,
                                                     weight = weight, 
                                                     user_url = '/update_info')



#Add ascent
@app.route("/add_bp", methods = ["GET", "POST"])
@login_required
def add_boulder_ascent():

    # get a connection, if a connect cannot be made an exception will be raised here
    url = urlparse(os.environ['DATABASE_URL'])
    conn = psycopg2.connect(database=url.path[1:],
                            user=url.username,
                            password=url.password,
                            host=url.hostname,
                            port=url.port)

    conn.autocommit = True

    # conn.cur will return a cur object, you can use this cur to perform queries
    cur = conn.cursor()
    current_user = session['user']

    cur.execute("SELECT id FROM users WHERE username = '{}'".format(current_user))
    user_id = cur.fetchall()[0][0]

    #Create autocomplete list
    cur.execute("SELECT name, crag_name FROM sectors ORDER BY crag_name;")
    areas = cur.fetchall()
    cs_list = []
    for area in areas:
        if area[0] == None:
            sector = 'None'
        else:
            sector = area[0].title()
        crag = area[1].title()
        cs_list.append({"name" : "{a}/{b}".format(a = crag,
                                                    b = sector)})

    cur.execute("SELECT id FROM users WHERE username = '{}'".format(current_user))
    user_id = cur.fetchall()[0][0]

    climb_type = 'boulder'


    #Doesn't actuall add a climb yet
    if request.method == "POST":
        success = 'Boulder added!'
        return render_template("add_boulder_ascent.html", success = success, 
                                                            cs_list = Markup(cs_list), 
                                                            username = current_user, 
                                                            user_url = '/update_info')

    #Information needed: user_id, climb_id (if exists), comment, log_date, log_type, suggested_grade
    #If climb_id doesn't exists, we may need to add crag information too

    return render_template("add_boulder_ascent.html", cs_list = Markup(cs_list), 
                                                        username = current_user, 
                                                        user_url = '/update_info')

#Add ascent
@app.route("/add_sport", methods = ["GET", "POST"])
@login_required
def add_sport_ascent():

    # get a connection, if a connect cannot be made an exception will be raised here
    url = urlparse(os.environ['DATABASE_URL'])
    conn = psycopg2.connect(database=url.path[1:],
                            user=url.username,
                            password=url.password,
                            host=url.hostname,
                            port=url.port)

    conn.autocommit = True

    # conn.cur will return a cur object, you can use this cur to perform queries
    cur = conn.cursor()
    current_user = session['user']

    cur.execute("SELECT id FROM users WHERE username = '{}'".format(current_user))
    user_id = cur.fetchall()[0][0]

    #Create autocomplete list
    cur.execute("SELECT name, crag_name FROM sectors ORDER BY crag_name;")
    areas = cur.fetchall()
    cs_list = []
    for area in areas:
        if area[0] == None:
            sector = 'None'
        else:
            sector = area[0].title()
        crag = area[1].title()
        cs_list.append({"name" : "{a}/{b}".format(a = crag,
                                                    b = sector)})

    cur.execute("SELECT id FROM users WHERE username = '{}'".format(current_user))
    user_id = cur.fetchall()[0][0]

    climb_type = 'sport'


    if request.method == "POST":
        success = 'Sport climb added!'
        print(request.form)
        return render_template("add_sport_ascent.html", success = success, 
                                                        cs_list = Markup(cs_list), 
                                                        username = current_user,
                                                        user_url = '/update_info')

    #Information needed: user_id, climb_id (if exists), comment, log_date, log_type, suggested_grade
    #If climb_id doesn't exists, we may need to add crag information too


    return render_template("add_sport_ascent.html", username = current_user,
                                                    user_url = '/update_info')

#Add ascent
@app.route("/add_trad", methods = ["GET", "POST"])
@login_required
def add_trad_ascent():

    # get a connection, if a connect cannot be made an exception will be raised here
    url = urlparse(os.environ['DATABASE_URL'])
    conn = psycopg2.connect(database=url.path[1:],
                            user=url.username,
                            password=url.password,
                            host=url.hostname,
                            port=url.port)

    conn.autocommit = True

    # conn.cur will return a cur object, you can use this cur to perform queries
    cur = conn.cursor()
    current_user = session['user']

    cur.execute("SELECT id FROM users WHERE username = '{}'".format(current_user))
    user_id = cur.fetchall()[0][0]

    #Create autocomplete list
    cur.execute("SELECT name, crag_name FROM sectors ORDER BY crag_name;")
    areas = cur.fetchall()
    cs_list = []
    for area in areas:
        if area[0] == None:
            sector = 'None'
        else:
            sector = area[0].title()
        crag = area[1].title()
        cs_list.append({"name" : "{a}/{b}".format(a = crag,
                                                    b = sector)})

    cur.execute("SELECT id FROM users WHERE username = '{}'".format(current_user))
    user_id = cur.fetchall()[0][0]

    climb_type = 'trad'


    if request.method == "POST":
        success = 'Trad route added!'
        print(request.form)
        return render_template("add_trad_ascent.html", success = success, 
                                                        cs_list = Markup(cs_list), 
                                                        username = current_user,
                                                        user_url = '/update_info')

    #Information needed: user_id, climb_id (if exists), comment, log_date, log_type, suggested_grade
    #If climb_id doesn't exists, we may need to add crag information too


    return render_template("add_trad_ascent.html", username = current_user,
                                                    user_url = '/update_info')

#Add ascent
@app.route("/import_ticklist", methods = ["GET", "POST"])
@login_required
def import_ticklist():

    # get a connection, if a connect cannot be made an exception will be raised here
    url = urlparse(os.environ['DATABASE_URL'])
    conn = psycopg2.connect(database = url.path[1:],
                            user = url.username,
                            password = url.password,
                            host = url.hostname,
                            port = url.port)

    conn.autocommit = True

    # conn.cur will return a cur object, you can use this cur to perform queries
    cur = conn.cursor()
    current_user = session['user']

    cur.execute("SELECT id FROM users WHERE username = '{}'".format(current_user))
    user_id = cur.fetchall()[0][0]

    if request.method == "POST":
        # if len(request.form['inputClimbs']) > 0:
        #     url = request.form['inputClimbs']
        if len(request.form['inputTicklist']) > 0:
            url = request.form['inputTicklist']

        html = BeautifulSoup(simple_get(url), 'html5lib')
        
        # if len(request.form['inputClimbs']) > 0:
        #     climb_rows = html.findAll("tr", {"class": "Height20"})
        if len(request.form['inputTicklist']) > 0:
            climb_rows = html.findAll('tr')

        areas = []

        #grades and grade_count are used when uploading your ticklist from 8A. Have to use this method to include the 
        #grades assigned by the user
        grades = []
        grade_count = 0
        for row in climb_rows:
            print(row)
            if len(request.form['inputTicklist']) > 0:
                if len(row) != 19:
                    if 'AscentPyramid' in str(row):
                        grade = str(row).replace('<tr><td>','').split('</td>')[0]
                        if len(grade) < 4:
                            grades.append(grade)

                    else:
                        if 'AscentListHeadRow' in str(row):
                            grade_count += 1


                if len(row) == 19:
                    x = 0
                    crag = None
                    sector = None
                    crag_only = None

                    for part in row:
                        #Ascent Date
                        if x == 1:
                            if '<nobr>' in str(part):
                                part = str(part).replace('<i>','')
                                date = part.split('<nobr>')[1][0:8]
                            else:
                                date = str(part).split('<i>')[1][0:8]

                            if int(date[0:2]) > 50:
                                year = int('19{}'.format(date[0:2]))
                            else:
                                year = int('20{}'.format(date[0:2]))
                            date = '{year}{date}'.format(year = year,
                                                         date = date[2:])

                        #Climb Name
                        elif x == 5:
                            climb_name = str(part).replace('</a></span></td>','').split('>')[-1].lower().replace("'",'&apos&')

                        #Crag
                        elif x == 9:
                            txt = str(part).replace('</span></td>','').replace('</a>','').split('>')[-1]
                            if len(txt.split(' / ')) > 1:
                                crag = txt.split(' / ')[0].lower().replace("'",'&apos&')
                                sector = txt.split(' / ')[1].lower().replace("'",'&apos&')

                            else:
                                crag_only = txt.lower().replace("'",'&apos&')


                        #Comment
                        elif x == 13:
                            comment = str(part).replace('</td>','').split('>')[-1].replace("'",'&apos&')

                        #Stars
                        elif x == 15:
                            stars = str(part).replace('<td valign="baseline">','').split('<')[0]

                            #Add data
                            if sector != None:
                                cur.execute("SELECT id FROM sectors WHERE name = '{}';".format(sector))
                            elif crag_only != None:
                                cur.execute("SELECT id FROM sectors WHERE crag_name = '{}';".format(crag_only))
                            else:
                                sys.exit()

                            results = cur.fetchall()

                            #----------------------------------------------------------------------
                            #If this is a new sector/crag
                            if len(results) == 0:
                                #Add the sector/crag
                                try:
                                    if sector != None:
                                        cur.execute("INSERT INTO sectors (name, crag_name) VALUES ('{sector}', '{crag_name}');".format(sector = sector,
                                                                                                                                        crag_name = crag))


                                        print('{a} - {b} added!'.format(a = sector,
                                                                        b = crag))
                                    elif crag_only != None:
                                        cur.execute("INSERT INTO sectors (crag_name) VALUES ('{crag_name}');".format(crag_name = crag_only))

                                        print('{a} added!'.format(a = crag))

                                    else:
                                        print('Abort 1')
                                        sys.exit()

                                except psycopg2.DatabaseError as error:
                                    if 'already exists' in str(error):
                                        print('{} already exists in db'.format(crag))
                                    else:
                                        print(error)

                                #Add the climb, then the ascent
                                if sector != None:
                                    #Get newly created sector_id
                                    cur.execute("SELECT id FROM sectors WHERE name = '{}';".format(sector))

                                elif crag_only != None:
                                    #Get newly created sector_id
                                    cur.execute("SELECT id FROM sectors WHERE crag_name = '{}' AND name IS NULL;".format(crag_only))

                                sector_id = int(cur.fetchall()[0][0])

                                #Insert the climb into climbs
                                cur.execute("INSERT INTO climbs (name, sector_id, climb_type) VALUES ('{name}', {sid}, '{ctype}');".format(name = climb_name,
                                                                                                                                            sid = int(sector_id),
                                                                                                                                            ctype = 'boulder'))

                                #Get newly created climb_id
                                cur.execute("SELECT id FROM climbs WHERE name = '{name}' and sector_id = {sid};".format(name = climb_name.replace("'", '&apos&'),
                                                                                                                        sid = int(sector_id)))
                                climb_id = cur.fetchall()[0][0]
                                print("{} added!".format(climb_name))

                                try:    
                                    #Insert tick
                                    cur.execute("INSERT INTO ticks (user_id, climb_id, comment, log_date, log_type, suggested_grade, stars) VALUES ('{user_id}', '{climb_id}', '{comment}', '{log_date}', '{log_type}', '{suggested_grade}', '{stars}')".format(user_id = int(user_id),
                                                                                                                                                                                                                                                                climb_id = int(climb_id),
                                                                                                                                                                                                                                                                comment = comment.replace("'",'&apos&'),
                                                                                                                                                                                                                                                                log_date = date,
                                                                                                                                                                                                                                                                log_type = 'send',
                                                                                                                                                                                                                                                                suggested_grade = font_to_v_boulder(grades[grade_count - 1]),
                                                                                                                                                                                                                                                                stars = len(stars)))

                                    print("Ascent of {} added!".format(climb_name))

                                except psycopg2.DatabaseError as error:
                                    if 'already exists' in str(error):
                                        print('"{}" already exists in db'.format(climb_name))
                                    else:
                                        print(error)


                            #----------------------------------------------------------------------
                            #If the sector/crag is in the DB and there's only one record
                            elif len(results) == 1:
                                sector_id = int(results[0][0])

                                #Check if the climb already exists
                                cur.execute("SELECT * FROM climbs WHERE name = '{name}' AND sector_id = '{sid}' AND climb_type = 'boulder';".format(name = climb_name,
                                                                                                                                                sid = sector_id))

                                climb_query = cur.fetchall()

                                if len(climb_query) == 0:
                                    #Insert the climb into climbs
                                    cur.execute("INSERT INTO climbs (name, sector_id, climb_type) VALUES ('{name}', {sid}, '{ctype}');".format(name = climb_name,
                                                                                                                                                sid = sector_id,
                                                                                                                                                ctype = 'boulder'))

                                    cur.execute("SELECT * FROM climbs WHERE name = '{name}' AND sector_id = '{sid}' AND climb_type = 'boulder';".format(name = climb_name,
                                                                                                                                                    sid = sector_id))

                                    climb_query = cur.fetchall()

                                climb_id = climb_query[0][0]

                                try:
                                    #Insert tick
                                    cur.execute("INSERT INTO ticks (user_id, climb_id, comment, log_date, log_type, suggested_grade, stars) VALUES ('{user_id}', '{climb_id}', '{comment}', '{log_date}', '{log_type}', '{suggested_grade}', '{stars}')".format(user_id = int(user_id),
                                                                                                                                                                                                                                                                climb_id = int(climb_id),
                                                                                                                                                                                                                                                                comment = comment,
                                                                                                                                                                                                                                                                log_date = date,
                                                                                                                                                                                                                                                                log_type = 'send',
                                                                                                                                                                                                                                                                suggested_grade = font_to_v_boulder(grades[grade_count - 1]),
                                                                                                                                                                                                                                                                stars = len(stars)))

                                    print("Ascent of {} added!".format(climb_name))


                                except psycopg2.DatabaseError as error:
                                    if 'already exists' in str(error):
                                        print('"{}" already exists in db'.format(climb_name))
                                    else:
                                        print(error)


                        x += 1
                    print('')



        for area in areas:
            print(area)
            cur.execute("SELECT id FROM sectors WHERE name = '{}';".format(area))
            sector_id = cur.fetchall()[0][0]
            for row in climb_rows:
                if row.a.contents[0] not in ['Advance Search', 'Grade']:
                    climb_name = row.a.contents[0].lower().replace('*','').replace("'","&apos&")
                    if len(row.text.split('/')) == 1:
                        continue
                    crag = row.text.split('/')[1][:-4].lower()
                    if crag[0] == ' ':
                        crag = crag[1:]

                    if crag == area:
                        try:
                            str(climb_name)
                        except:
                            continue

                        # try:
                        #     cur.execute("INSERT INTO climbs (name, sector_id, climb_type) VALUES ('{name}', {sid}, '{ctype}');".format(name = climb_name,
                        #                                                                                                                 sid = sector_id,
                        #                                                                                                                 ctype = 'boulder'))
                        #     print "{} added!".format(climb_name)
                        # except psycopg2.DatabaseError as error:
                        #     if 'already exists' in str(error):
                        #         print '"{}" already exists in db'.format(climb_name)
                        #     else:
                        #         print error

            print('')

        return render_template("import_ticklist.html", success = 'Ticklist imported!', 
                                                        username = current_user,
                                                        user_url = '/update_info')

    return render_template("import_ticklist.html", username = current_user,
                                                    user_url = '/update_info')

#Add ascent
@app.route("/climb/<climb_id>", methods = ["GET", "POST"])
@login_required
def climb_page(climb_id):
    # get a connection, if a connect cannot be made an exception will be raised here
    url = urlparse(os.environ['DATABASE_URL'])
    conn = psycopg2.connect(database=url.path[1:],
                            user=url.username,
                            password=url.password,
                            host=url.hostname,
                            port=url.port)

    conn.autocommit = True

    # conn.cur will return a cur object, you can use this cur to perform queries
    cur = conn.cursor()
    current_user = session['user']

    cur.execute("SELECT id FROM users WHERE username = '{}'".format(current_user))
    user_id = cur.fetchall()[0][0]

    cur.execute("SELECT users.username, ticks.suggested_grade, ticks.log_date, climbs.avg_grade, sectors.name, sectors.crag_name FROM ticks INNER JOIN users ON ticks.user_id = users.id INNER JOIN climbs ON ticks.climb_id = climbs.id INNER JOIN sectors ON climbs.crag = sectors.id WHERE climbs.id = {};".format(climb_id))

    #------------------------------------------
    #Ticklist table creation
    ticklist_columns = [desc[0] for desc in cur.description]
    
    table= '<thead class= "thead-dark"><tr>'
    for header in ticklist_columns:
        table += '<th>{header}</th>'.format(header= header.replace('_',' ').title())

    table += '</tr></thead><tbody>'

    ticks = cur.fetchall()

    for row in ticks:
        for num, item in enumerate(row):
            if num in [ticklist_columns.index('suggested_grade'), ticklist_columns.index('avg_grade')]:
                table += '<td>V{a}</td>'.format(a = item)
            elif num == ticklist_columns.index('log_date'):
                table += '<td>{a}</td>'.format(a = item)
            elif num == ticklist_columns.index('username'):
                table += '<td>{a}</td>'.format(a = item)
            else:
                table += '<td>{a}</td>'.format(a = item.title())

    table += '</tr></body>'


    return render_template("climb_page.html", main_page = Markup(table), 
                                                username = current_user,
                                                user_url = '/update_info')


#Need a page to update user info
@app.route("/update_info", methods = ["GET", "POST"])
@login_required
def update_info():
    # get a connection, if a connect cannot be made an exception will be raised here
    url = urlparse(os.environ['DATABASE_URL'])
    conn = psycopg2.connect(database=url.path[1:],
                            user=url.username,
                            password=url.password,
                            host=url.hostname,
                            port=url.port)

    conn.autocommit = True
    cur = conn.cursor()

    current_user = session['user']
    cur.execute("SELECT id FROM users WHERE username = '{}'".format(current_user))
    user_id = cur.fetchall()[0][0]

    # conn.cur will return a cur object, you can use this cur to perform queries
    cur = conn.cursor()

    #------------------------------------------
    #User info
    cur.execute("SELECT firstname, lastname, dob, height, weight, email FROM users WHERE id = {};".format(user_id))
    info = cur.fetchall()[0]
    firstname = info[0]
    lastname = info[1]
    dob = info[2]
    height = info[3]
    weight = info[4]
    email = info[5]

    if request.method == "POST":
        #Check for user information update:
        if 'inputFirstName' in request.form:
            try:
                cur.execute("UPDATE users SET firstname = '%s', lastname = '%s', email = '%s', dob = '%s', height = %i, weight = %i  WHERE id = %i;".format(request.form['inputFirstName'],
                                                                                                                                                            request.form['inputLastName'],
                                                                                                                                                            request.form['inputEmail'],
                                                                                                                                                            request.form['inputDOB'],
                                                                                                                                                            height,
                                                                                                                                                            weight,
                                                                                                                                                            user_id))

                cur.execute("SELECT firstname, lastname, dob, height, weight, email FROM users WHERE id = {};".format(user_id))
                info = cur.fetchall()[0]
                firstname = info[0]
                lastname = info[1]
                dob = info[2]
                height = info[3]
                weight = info[4]
                email = info[5]

                return render_template("update_info.html", username = current_user,
                                                     fname = firstname,
                                                     lname = lastname,
                                                     dob = dob,
                                                     height = height,
                                                     weight = weight, 
                                                     email = email,
                                                     user_url = '/update_info',
                                                     info_success = 'Information Updated!')

            except psycopg2.DatabaseError as error:
                return render_template("update_info.html", username = current_user,
                                                     fname = firstname,
                                                     lname = lastname,
                                                     dob = dob,
                                                     height = height,
                                                     weight = weight, 
                                                     email = email,
                                                     user_url = '/update_info',
                                                     info_error = 'Information Failed To Update!')



        #Check for password update
        elif 'inputPassword1' in request.form:
            #Make sure passwords match and if so, update password
            if request.form['inputPassword1'] == request.form['inputPassword2']:
                new_password = sha256_crypt.encrypt(str(request.form['inputPassword1']))
                try: 
                    cur.execute("UPDATE users SET password = '%s' WHERE id = '{Id}';".format(new_password,
                                                                                            user_id))

                    return render_template("update_info.html", username = current_user,
                                                                 fname = firstname,
                                                                 lname = lastname,
                                                                 dob = dob,
                                                                 height = height,
                                                                 weight = weight, 
                                                                 email = email,
                                                                 user_url = '/update_info',
                                                                 password_success = 'Password updated!')

                except psycopg2.DatabaseError as error:
                    return render_template("update_info.html", username = current_user,
                                                                 fname = firstname,
                                                                 lname = lastname,
                                                                 dob = dob,
                                                                 height = height,
                                                                 weight = weight, 
                                                                 email = email,
                                                                 user_url = '/update_info',
                                                                 password_error = 'Update failed!')

            else:
                return render_template("update_info.html", username = current_user,
                                                     fname = firstname,
                                                     lname = lastname,
                                                     dob = dob,
                                                     height = height,
                                                     weight = weight, 
                                                     email = email,
                                                     user_url = '/update_info',
                                                     password_error = 'New Passwords Did Not Match!')


    return render_template("update_info.html", username = current_user,
                                                     fname = firstname,
                                                     lname = lastname,
                                                     dob = dob,
                                                     height = height,
                                                     weight = weight, 
                                                     email = email,
                                                     user_url = '/update_info')





























# @app.route("/admin", methods = ["GET", "POST"])
# @login_required
# def admin_page():

#     #--------------
#     #Will eventually want to assert that user is an admin to access the page
#     #--------------

#     # get a connection, if a connect cannot be made an exception will be raised here
#     url = urlparse.urlparse(os.environ['DATABASE_URL'])
#     conn = psycopg2.connect(database = url.path[1:],
#                             user = url.username,
#                             password = url.password,
#                             host = url.hostname,
#                             port = url.port)

#     conn.autocommit = True

#     # conn.cur will return a cur object, you can use this cur to perform queries
#     cur = conn.cursor()

#     current_user = thwart(session['user'])

#     cur.execute("SELECT id FROM users WHERE username = '{}'".format(current_user))
#     user_id = cur.fetchall()[0][0]

#     if request.method == "POST":
#         if len(request.form['inputClimbs']) > 0:
#             url = request.form['inputClimbs']
#         elif len(request.form['inputTicklist']) > 0:
#             url = request.form['inputTicklist']

#         html = BeautifulSoup(simple_get(url), 'html5lib')
        
#         if len(request.form['inputClimbs']) > 0:
#             climb_rows = html.findAll("tr", {"class": "Height20"})
#         elif len(request.form['inputTicklist']) > 0:
#             climb_rows = html.findAll('tr')

#         areas = []

#         #grades and grade_count are used when uploading your ticklist from 8A. Have to use this method to include the 
#         #grades assigned by the user
#         grades = []
#         grade_count = 0
#         for row in climb_rows:
#             if len(request.form['inputClimbs']) > 0:
#                 if row.a.contents[0] not in ['Advance Search', 'Grade']:
#                     if len(row.text.split('/')) == 1:
#                         continue
#                     crag = row.text.split('/')[1][:-4].lower().replace("'","&apos&")
#                     if crag[0] == ' ':
#                         crag = crag[1:]

#                     if crag not in areas:
#                         try:
#                             str(crag)
#                         except:
#                             continue

#                     # try:
#                     #     cur.execute("INSERT INTO sectors (name, state, country, crag_name) VALUES ('{sector}', '{state}', '{country}', '{crag_name}');".format(sector = crag,
#                     #                                                                                                                                             state = 'ca',
#                     #                                                                                                                                             country = 'usa',
#                     #                                                                                                                                             crag_name = 'yosemite valley'))
                    
#                     #     print '{} added!'.format(crag)

#                     # except psycopg2.DatabaseError as error:
#                     #     if 'already exists' in str(error):
#                     #         print '{} already exists in db'.format(crag)
#                     #     else:
#                     #         print error

#                     areas.append(crag)

#             elif len(request.form['inputTicklist']) > 0:
#                 if len(row) != 19:
#                     if 'AscentPyramid' in str(row):
#                         grade = str(row).replace('<tr><td>','').split('</td>')[0]
#                         if len(grade) < 4:
#                             grades.append(grade)

#                     else:
#                         if 'AscentListHeadRow' in str(row):
#                             grade_count += 1


#                 if len(row) == 19:
#                     x = 0
#                     crag = None
#                     sector = None
#                     crag_only = None

#                     for part in row:
#                         #Ascent Date
#                         if x == 1:
#                             if '<nobr>' in str(part):
#                                 part = str(part).replace('<i>','')
#                                 date = part.split('<nobr>')[1][0:8]
#                             else:
#                                 date = str(part).split('<i>')[1][0:8]

#                             if int(date[0:2]) > 50:
#                                 year = int('19{}'.format(date[0:2]))
#                             else:
#                                 year = int('20{}'.format(date[0:2]))
#                             date = '{year}{date}'.format(year = year,
#                                                          date = date[2:])

#                         #Climb Name
#                         elif x == 5:
#                             climb_name = str(part).replace('</a></span></td>','').split('>')[-1].lower().replace("'",'&apos&')

#                         #Crag
#                         elif x == 9:
#                             txt = str(part).replace('</span></td>','').replace('</a>','').split('>')[-1]
#                             if len(txt.split(' / ')) > 1:
#                                 crag = txt.split(' / ')[0].lower().replace("'",'&apos&')
#                                 sector = txt.split(' / ')[1].lower().replace("'",'&apos&')

#                             else:
#                                 crag_only = txt.lower().replace("'",'&apos&')


#                         #Comment
#                         elif x == 13:
#                             comment = str(part).replace('</td>','').split('>')[-1].replace("'",'&apos&')

#                         #Stars
#                         elif x == 15:
#                             stars = str(part).replace('<td valign="baseline">','').split('<')[0]

#                             #Add data
#                             if sector != None:
#                                 cur.execute("SELECT id FROM sectors WHERE name = '{}';".format(sector))
#                             elif crag_only != None:
#                                 cur.execute("SELECT id FROM sectors WHERE crag_name = '{}';".format(crag_only))
#                             else:
#                                 sys.exit()

#                             results = cur.fetchall()

#                             #----------------------------------------------------------------------
#                             #If this is a new sector/crag
#                             if len(results) == 0:
#                                 #Add the sector/crag
#                                 try:
#                                     if sector != None:
#                                         cur.execute("INSERT INTO sectors (name, crag_name) VALUES ('{sector}', '{crag_name}');".format(sector = sector,
#                                                                                                                                         crag_name = crag))


#                                         print '{a} - {b} added!'.format(a = sector,
#                                                                         b = crag)
#                                     elif crag_only != None:
#                                         cur.execute("INSERT INTO sectors (crag_name) VALUES ('{crag_name}');".format(crag_name = crag_only))

#                                         print '{a} added!'.format(a = crag)

#                                     else:
#                                         print 'Abort 1'
#                                         sys.exit()

#                                 except psycopg2.DatabaseError as error:
#                                     if 'already exists' in str(error):
#                                         print '{} already exists in db'.format(crag)
#                                     else:
#                                         print error

#                                 #Add the climb, then the ascent
#                                 if sector != None:
#                                     #Get newly created sector_id
#                                     cur.execute("SELECT id FROM sectors WHERE name = '{}';".format(sector))

#                                 elif crag_only != None:
#                                     #Get newly created sector_id
#                                     cur.execute("SELECT id FROM sectors WHERE crag_name = '{}' AND name IS NULL;".format(crag_only))

#                                 sector_id = int(cur.fetchall()[0][0])

#                                 #Insert the climb into climbs
#                                 cur.execute("INSERT INTO climbs (name, sector_id, climb_type) VALUES ('{name}', {sid}, '{ctype}');".format(name = climb_name,
#                                                                                                                                             sid = int(sector_id),
#                                                                                                                                             ctype = 'boulder'))

#                                 #Get newly created climb_id
#                                 cur.execute("SELECT id FROM climbs WHERE name = '{name}' and sector_id = {sid};".format(name = climb_name.replace("'", '&apos&'),
#                                                                                                                         sid = int(sector_id)))
#                                 climb_id = cur.fetchall()[0][0]
#                                 print "{} added!".format(climb_name)

#                                 try:    
#                                     #Insert tick
#                                     cur.execute("INSERT INTO ticks (user_id, climb_id, comment, log_date, log_type, suggested_grade, stars) VALUES ('{user_id}', '{climb_id}', '{comment}', '{log_date}', '{log_type}', '{suggested_grade}', '{stars}')".format(user_id = int(user_id),
#                                                                                                                                                                                                                                                                 climb_id = int(climb_id),
#                                                                                                                                                                                                                                                                 comment = comment.replace("'",'&apos&'),
#                                                                                                                                                                                                                                                                 log_date = date,
#                                                                                                                                                                                                                                                                 log_type = 'send',
#                                                                                                                                                                                                                                                                 suggested_grade = font_to_v_boulder(grades[grade_count - 1]),
#                                                                                                                                                                                                                                                                 stars = len(stars)))

#                                     print "Ascent of {} added!".format(climb_name)

#                                 except psycopg2.DatabaseError as error:
#                                     if 'already exists' in str(error):
#                                         print '"{}" already exists in db'.format(climb_name)
#                                     else:
#                                         print error


#                             #----------------------------------------------------------------------
#                             #If the sector/crag is in the DB and there's only one record
#                             elif len(results) == 1:
#                                 sector_id = int(results[0][0])

#                                 #Check if the climb already exists
#                                 cur.execute("SELECT * FROM climbs WHERE name = '{name}' AND sector_id = '{sid}' AND climb_type = 'boulder';".format(name = climb_name,
#                                                                                                                                                 sid = sector_id))

#                                 climb_query = cur.fetchall()

#                                 if len(climb_query) == 0:
#                                     #Insert the climb into climbs
#                                     cur.execute("INSERT INTO climbs (name, sector_id, climb_type) VALUES ('{name}', {sid}, '{ctype}');".format(name = climb_name,
#                                                                                                                                                 sid = sector_id,
#                                                                                                                                                 ctype = 'boulder'))

#                                     cur.execute("SELECT * FROM climbs WHERE name = '{name}' AND sector_id = '{sid}' AND climb_type = 'boulder';".format(name = climb_name,
#                                                                                                                                                     sid = sector_id))

#                                     climb_query = cur.fetchall()

#                                 climb_id = climb_query[0][0]

#                                 try:
#                                     #Insert tick
#                                     cur.execute("INSERT INTO ticks (user_id, climb_id, comment, log_date, log_type, suggested_grade, stars) VALUES ('{user_id}', '{climb_id}', '{comment}', '{log_date}', '{log_type}', '{suggested_grade}', '{stars}')".format(user_id = int(user_id),
#                                                                                                                                                                                                                                                                 climb_id = int(climb_id),
#                                                                                                                                                                                                                                                                 comment = comment,
#                                                                                                                                                                                                                                                                 log_date = date,
#                                                                                                                                                                                                                                                                 log_type = 'send',
#                                                                                                                                                                                                                                                                 suggested_grade = font_to_v_boulder(grades[grade_count - 1]),
#                                                                                                                                                                                                                                                                 stars = len(stars)))

#                                     print "Ascent of {} added!".format(climb_name)


#                                 except psycopg2.DatabaseError as error:
#                                     if 'already exists' in str(error):
#                                         print '"{}" already exists in db'.format(climb_name)
#                                     else:
#                                         print error


#                         x += 1
#                     print ''



#         for area in areas:
#             print area
#             cur.execute("SELECT id FROM sectors WHERE name = '{}';".format(area))
#             sector_id = cur.fetchall()[0][0]
#             for row in climb_rows:
#                 if row.a.contents[0] not in ['Advance Search', 'Grade']:
#                     climb_name = row.a.contents[0].lower().replace('*','').replace("'","&apos&")
#                     if len(row.text.split('/')) == 1:
#                         continue
#                     crag = row.text.split('/')[1][:-4].lower()
#                     if crag[0] == ' ':
#                         crag = crag[1:]

#                     if crag == area:
#                         try:
#                             str(climb_name)
#                         except:
#                             continue

#                         # try:
#                         #     cur.execute("INSERT INTO climbs (name, sector_id, climb_type) VALUES ('{name}', {sid}, '{ctype}');".format(name = climb_name,
#                         #                                                                                                                 sid = sector_id,
#                         #                                                                                                                 ctype = 'boulder'))
#                         #     print "{} added!".format(climb_name)
#                         # except psycopg2.DatabaseError as error:
#                         #     if 'already exists' in str(error):
#                         #         print '"{}" already exists in db'.format(climb_name)
#                         #     else:
#                         #         print error

#             print ''

#         return render_template('admin_page.html', success = 'Climbs added', username = current_user)

#     return render_template('admin_page.html', username = current_user)

# # # Update areas json
# @app.route("/admin", methods = ["GET", "POST"])
# def admin_page():
#     url = urlparse.urlparse(os.environ['DATABASE_URL'])
#     conn = psycopg2.connect(database=url.path[1:],
#                             user=url.username,
#                             password=url.password,
#                             host=url.hostname,
#                             port=url.port)
#     conn.autocommit = True

#     # conn.cur will return a cur object, you can use this cur to perform queries
#     cur = conn.cursor()

#     cur.execute("SELECT id, name, crag FROM sectors;")

#     all_areas = cur.fetchall()

#     with open('{path}/areas/areas.json'.format(path= os.path.dirname(os.path.realpath(__file__))), 'w') as areas_json:
#         areas = []
#         for line in all_areas:
#             sid = line[0]
#             sector = line[1]
#             crag = line[2]

#             new_data = {"sector": sector.title(),
#                         "crag": crag.title(),
#                         "sid": sid}

#             areas.append(new_data)

#         json.dump(areas, areas_json)
#     cur.close()
#     conn.close()
#     gc.collect()
#     return render_template('error.html', error= 'Areas updated!')










    #Get a list of sectors and crags
    # cur.execute('SELECT id, name, sector FROM crags;')
#     sectors_crags= []
#     for place in cur.fetchall():
#         if place not in sectors_crags:
#             sectors_crags.append(place)

#     if request.method == "POST":
#         #Climb is added
#         if 'climb' in request.form:
#             climb = request.form['climb']
#             grade = request.form['grade']
#             sent_boo= request.form['sent_boo']
#             privacy= request.form['privacy']
#             sector= request.form['sector']
#             crag= request.form['crag']
#             comment= request.form['comment']
#             date= request.form['date']
#             lat = float(request.form['latitude'])
#             lon = float(request.form['longitude'])

#             cur.execute("SELECT * FROM boulders;")
#             boulders= cur.fetchall()
#             for boulder in boulders:
#                 if boulder[1].lower()== climb.lower() and boulder[7].lower()== sector.lower():
#                     existing_climb= boulder[1]
#                     existing_lat= boulder[3]
#                     existing_lon= boulder[4]
#                     existing_sector= boulder[7]
#                     existing_crag= boulder[8]
            

#             if 'existing_climb' in locals():
#                 cur.execute('''INSERT INTO boulders (username, climb, grade, latitude, longitude, sent_boo, privacy, sector, crag, comment, _date)
#                                 VALUES ('{climber}', '{climb}', '{grade}', '{lat}', '{lon}', '{sent}', '{privacy}', '{sector}', '{crag}', $${comment}$$, '{Date}');'''.format(climber= thwart(session['user']),
#                                                                                                                                                                               climb= thwart(existing_climb),
#                                                                                                                                                                               grade= int(grade),
#                                                                                                                                                                               lat= existing_lat,
#                                                                                                                                                                               lon= existing_lon, 
#                                                                                                                                                                               sent= sent_boo,
#                                                                                                                                                                               privacy= thwart(privacy), 
#                                                                                                                                                                               sector= thwart(existing_sector),
#                                                                                                                                                                               crag= thwart(existing_crag),
#                                                                                                                                                                               comment= thwart(comment),
#                                                                                                                                                                               Date= date))
#             else:
#                 cur.execute('''INSERT INTO boulders (username, climb, grade, latitude, longitude, sent_boo, privacy, sector, crag, comment, _date)
#                                 VALUES ('{climber}', '{climb}', '{grade}', '{lat}', '{lon}', '{sent}', '{privacy}', '{sector}', '{crag}', $${comment}$$, '{Date}');'''.format(climber= thwart(session['user']),
#                                                                                                                                                                               climb= thwart(climb),
#                                                                                                                                                                               grade= int(grade),
#                                                                                                                                                                               lat= lat,
#                                                                                                                                                                               lon= lon, 
#                                                                                                                                                                               sent= sent_boo,
#                                                                                                                                                                               privacy= thwart(privacy), 
#                                                                                                                                                                               sector= thwart(sector),
#                                                                                                                                                                               crag= thwart(crag),
#                                                                                                                                                                               comment= thwart(comment),
#                                                                                                                                                                               Date= date))

#         #Searching for a specfic crag
#         elif 'search_areas' in request.form:
#             with open('{path}/areas/areas.json'.format(path= os.path.dirname(os.path.realpath(__file__)))) as areas_json:    
#                 areas = json.load(areas_json)
#                 for area in areas:
#                     #Limit map and ticklist to sector
#                     if area['sector'].lower()== request.form['search_areas'].lower():
#                         sector= area['sector']
#                         lat= area['latitude']
#                         lon= area['longitude']
#                         map_extent= 'changeExtent({lat}, {lon}, 16);'.format(lat= lat,
#                                                                              lon= lon)
#                         cur.execute("SELECT DISTINCT on (climb, sector, crag) climb, oid, grade, latitude, longitude, sector, crag FROM boulders WHERE sector= '{a}';".format(a= thwart(sector)))
#                         all_boulders= cur.fetchall()

#                 #If map_extent isn't in locals, that means the user is searching for a crag, not a sector
#                 if 'map_extent' not in locals():
#                     lats= []
#                     longs= []
#                     for area in areas:
#                         if area['crag'].lower()== request.form['search_areas'].lower():
#                             crag= area['crag']
#                             lats.append(float(area['latitude']))
#                             longs.append(float(area['longitude']))
#                     #To get the map extent for a crag, we're going to create a lat/long based on the min and max coordinates
#                     #If there's only one sector at the crag, we just use those coordinates
#                     if len(lats) == 1:
#                         lat= lats[0]
#                         lon= longs[0]

#                     elif len(lats) > 1:
#                         lat= (max(lats) + min(lats))/2
#                         lon= (max(longs) + min(longs))/2 

#                     #If it's empty, that means they searched for a crag that doesn't exist, so we need to send the error message    
#                     else:
#                         return render_template('error.html', error= "You searched for a crag/sector that doesn't exists!")

#                     map_extent= 'changeExtent({lat}, {lon}, 12);'.format(lat= lat,
#                                                                          lon= lon)

#                     cur.execute("SELECT DISTINCT on (climb, sector, crag) climb, oid, grade, latitude, longitude, sector, crag FROM boulders WHERE crag= '{a}';".format(a= thwart(crag)))
#                     all_boulders= cur.fetchall()

#         #Search the map for specific coordinates
#         elif 'search_coords' in request.form:
#             coordinates= request.form['search_coords'].lower()
#             if any(char in coordinates for char in ('n','e','s','w')):
#                 lat= coordinates.split(',')[0]
#                 lat_split= re.split('''[ "']+''',lat)
#                 lon= coordinates.split(',')[1]
#                 lon_split= re.split('''[ "']+''',lon)
#                 if lon_split[0]== '':
#                     lon_split= lon_split[1:]

#                 map_extent= 'changeExtent({lat}, {lon}, 12);'.format(lat= dm2dd(lat_split[1], lat_split[2], lat_split[0]),
#                                                                      lon= dm2dd(lon_split[1], lon_split[2], lon_split[0]))

#             else:
#                 coordinates= coordinates.replace(' ','')
#                 map_extent= 'changeExtent({lat}, {lon}, 12);'.format(lat= coordinates.split(',')[0],
#                                                                      lon= coordinates.split(',')[1])

#         else:
#             print 'New request type.'
#             print request.form


#     if 'all_boulders' not in locals():
#         cur.execute("SELECT DISTINCT on (climb, sector, crag) climb, oid, grade, latitude, longitude, sector, crag FROM boulders;")

#         all_boulders = cur.fetchall()

#     #------------------------------------------
#     #Ticklist table creation
#     ticklist_columns= [desc[0] for desc in cur.description]
#     ticklist_columns.remove('oid')
    
#     table= '<thead><tr>'
#     for header in ticklist_columns:
#         table += '<th>{header}</th>'.format(header= header.title())

#     table += '</tr></thead><tbody>'

#     for row in all_boulders:
#         table += '<tr>'
#         oid= row[1]
#         row= row[0:1] + row[2:]
#         for num, item in enumerate(row):
#             if num == 0:
#                 link= '{a}_{b}'.format(a= item.replace(' ','$$$'),
#                                        b= oid)
#                 table += '<td><a href= /{a}>{b}</a></td>'.format(a= link,
#                                                                  b= item)
#             elif num == 1:
#                 table += '<td>V{a}</td>'.format(a= item)
#             else:
#                 table += '<td>{a}</td>'.format(a= item)

#     table += '</tr></body>'
#     #------------------------------------------

#     boulders = list()
#     boulder_info = ""
#     for record in all_boulders:
#         climb = str(record[0])
#         boulder_id = str(record[1])
#         grade = str(record[2])
#         lat = str(record[3])
#         lon = str(record[4])

#         # if username== str(session['user']):
#         #     boulder_info += Markup('''
#         #                         var marker_{id} = L.marker([{lat}, {lon}],
#         #                                 {{
#         #                                     icon: redMarker
#         #                                     }}
#         #                                 );
#         #                         var popup_{id} = L.popup({{maxWidth: '300'}});
#         #                         var html_{id} = ('<div id="html_{id}" style="width: 100.0%; height: 100.0%;">{climb}</div>')[0];
#         #                         popup_{id}.setContent(html_{id});
#         #                         marker_{id}.bindPopup("{popup}<br>{v}");'''.format(id=boulder_id,
#         #                                                                            climb=climb,
#         #                                                                            lat=lat,
#         #                                                                            lon=lon,
#         #                                                                            popup= climb,
#         #                                                                            v= grade))
#         # else:
#         boulder_info += Markup('''
#                             var marker_{id} = L.marker([{lat}, {lon}],
#                                     {{
#                                         icon: greenMarker
#                                         }}
#                                     );
#                             var popup_{id} = L.popup({{maxWidth: '300'}});
#                             var html_{id} = ('<div id="html_{id}" style="width: 100.0%; height: 100.0%;">{climb}</div>')[0];
#                             popup_{id}.setContent(html_{id});
#                             marker_{id}.bindPopup("{popup}<br>{v}");'''.format(id=boulder_id,
#                                                                                climb=climb,
#                                                                                lat=lat,
#                                                                                lon=lon,
#                                                                                popup= climb,
#                                                                                v= grade))
#         boulders.append('marker_{id}'.format(id=boulder_id))
#     boulder_info += Markup('''
#                            var boulders= [{a}]'''.format(a= ', '.join(boulders)))

#     #Create the autocomplete list
#     cur.execute("SELECT crag, sector FROM boulders;")
#     boulders= cur.fetchall()
#     autocomplete_list= []
#     for boulder_set in boulders:
#         if boulder_set[0] not in autocomplete_list:
#             autocomplete_list.append(boulder_set[0])
#         if boulder_set[1] not in autocomplete_list:
#             autocomplete_list.append(boulder_set[1])

#     cur.close()
#     conn.close()
#     gc.collect()

#     if 'map_extent' in locals():
#         return render_template("boulder_map.html", Boulder_Info=Markup(boulder_info), table= Markup(table), Map_Extent= Markup(map_extent), autocomplete_list= Markup(autocomplete_list))
#     else:
#         return render_template("boulder_map.html", Boulder_Info=Markup(boulder_info), table= Markup(table), autocomplete_list= Markup(autocomplete_list))


# #Page for a specific climb
# @app.route("/<climb>", methods=["GET", "POST"])
# @login_required
# def climb_page(climb):
#     #I need a better way to deal with this...
#     if climb== 'favicon.ico':
#         table= ''
#         boulder_info= ''

#     else:
#         climb_name= climb.split('_')[0].replace('$$$',' ')
#         oid= int(climb.split('_')[1].replace('$$$',' '))
#         # get a connection, if a connect cannot be made an exception will be raised here
#         url = urlparse.urlparse(os.environ['DATABASE_URL'])
#         conn= psycopg2.connect(database=url.path[1:],
#                                 user=url.username,
#                                 password=url.password,
#                                 host=url.hostname,
#                                 port=url.port)

#         conn.autocommit = True

#         cur = conn.cur()

#         cur.execute("SELECT climb, sector, crag, latitude, longitude FROM boulders WHERE oid = '{a}';".format(a= oid))
#         all_boulders= cur.fetchall()[0]
#         sector= all_boulders[1]
#         crag= all_boulders[2]
#         latitude= float(all_boulders[3])
#         longitude= float(all_boulders[4])

#         #Add an ascent/project on the climb page
#         if request.method == "POST":
#             grade = request.form['grade']
#             sent_boo= request.form['sent_boo']
#             privacy= request.form['privacy']
#             comment= request.form['comment']
#             date= request.form['date']

#             cur.execute('''INSERT INTO boulders (username, climb, grade, latitude, longitude, sent_boo, privacy, sector, crag, comment, _date)
#                                 VALUES ('{climber}', '{climb}', '{grade}', '{lat}', '{lon}', '{sent}', '{privacy}', '{sector}', '{crag}', $${comment}$$, '{Date}');'''.format(climber= thwart(session['user']),
#                                                                                                                                                                               climb= climb_name,
#                                                                                                                                                                               grade= int(grade),
#                                                                                                                                                                               lat= latitude,
#                                                                                                                                                                               lon= longitude, 
#                                                                                                                                                                               sent= sent_boo,
#                                                                                                                                                                               privacy= thwart(privacy), 
#                                                                                                                                                                               sector= sector,
#                                                                                                                                                                               crag= crag,
#                                                                                                                                                                               comment= thwart(comment),
#                                                                                                                                                                               Date= date))

#         cur.execute("SELECT * FROM boulders WHERE climb = '{a}' AND sector = '{b}' AND crag = '{c}';".format(a= climb_name,
#                                                                                                                 b= sector,
#                                                                                                                 c= crag))

#         all_boulders = cur.fetchall()

#         ticklist_columns= [desc[0] for desc in cur.description]
#         ticklist_columns.remove('latitude')
#         ticklist_columns.remove('longitude')
#         ticklist_columns.remove('sent_boo')
#         ticklist_columns.remove('privacy')
        
#         table= '<thead><tr>'
#         for header in ticklist_columns:
#             if header== '_date':
#                 header= 'date sent'
#             table += '<th>{header}</th>'.format(header= header.title())

#         table += '</tr></thead><tbody>'

#         for row in all_boulders:
#             table += '<tr>'
#             for num, item in enumerate(row):
#                 if num== 2:
#                     table += '<td>V{a}</td>'.format(a= item)
#                 elif num== 8:
#                     table += "<td>{a}</td>".format(a= item)
#                 elif num in (0,1,7,9,10):
#                     table += '<td>{a}</td>'.format(a= item)

#         table += '</tr></body>'

#         boulders = list()
#         boulder_info = ""
#         for record in all_boulders:
#             username= str(record[0])
#             climb = str(record[1])
#             grade= 'V' + str(record[2])
#             lat = str(record[3])
#             lon = str(record[4])

#             boulder_info += Markup('''
#                                 var marker_{id} = L.marker([{lat}, {lon}],
#                                         {{
#                                             icon: greenMarker
#                                             }}
#                                         );
#                                 var popup_{id} = L.popup({{maxWidth: '300'}});
#                                 var html_{id} = ('<div id="html_{id}" style="width: 100.0%; height: 100.0%;">{climb}</div>')[0];
#                                 popup_{id}.setContent(html_{id});
#                                 marker_{id}.bindPopup("{popup}<br>{v}");'''.format(id=1,
#                                                                                    climb=climb,
#                                                                                    lat=lat,
#                                                                                    lon=lon,
#                                                                                    popup= climb,
#                                                                                    v= grade))
#             boulders.append('marker_{id}'.format(id=1))
#         boulder_info += Markup('''
#                             var boulders = L.layerGroup([{boulders}]);
#                             '''.format(boulders=', '.join(boulders)))

#         cur.close()
#         conn.close()
#         gc.collect()
#     return render_template('climb_page.html', table= Markup(table), boulder_info= Markup(boulder_info))

# #Update areas json
# @app.route("/admin", methods=["GET", "POST"])
# def admin_page():
#     url = urlparse.urlparse(os.environ['DATABASE_URL'])
#     conn= psycopg2.connect(database=url.path[1:],
#                             user=url.username,
#                             password=url.password,
#                             host=url.hostname,
#                             port=url.port)
#     conn.autocommit= True

#     # conn.cur will return a cur object, you can use this cur to perform queries
#     cur = conn.cur()

#     cur.execute("SELECT sector, crag, latitude, longitude FROM boulders ORDER BY crag, sector;")

#     all_boulders = cur.fetchall()

#     places= []

#     for climb in all_boulders:
#         sector= climb[0]
#         crag= climb[1]
#         comb= '{a}$$${b}'.format(a= sector,
#                                  b= crag)
#         if comb not in places:
#             places.append(comb)

#     with open('{path}/areas/areas.json'.format(path= os.path.dirname(os.path.realpath(__file__))), 'w') as areas_json:
#         areas= []
#         for comb in places:
#             sector= comb.split('$$$')[0]
#             crag= comb.split('$$$')[1]
#             lats= []
#             longs= []
#             for climb in all_boulders:
#                 if climb[0]== sector and climb[1]== crag:
#                     lats.append(float(climb[2]))
#                     longs.append(float(climb[3]))

#             new_data= {"sector": sector.title(),
#                         "crag": crag.title(),
#                         "latitude": sum(lats)/len(lats),
#                         "longitude": sum(longs)/len(longs)}

#             areas.append(new_data)
#         json.dump(areas, areas_json)

#     cur.close()
#     conn.close()
#     gc.collect()
#     return render_template('error.html', error= 'Areas updated!')

# # #Error page
# # @app.route("/error", methods=["GET", "POST"])
# # @login_required
# # def error_page():

if __name__ == "__main__":
    app.run()
