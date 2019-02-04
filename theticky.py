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
from MySQLdb import escape_string as thwart
import gc
import requests

from functools import wraps
import argparse
import folium
from functools import wraps
import urlparse
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

url = urlparse.urlparse(os.environ['DATABASE_URL'])

#logout page
@app.route('/logout')
def logout():
    session.clear()
    gc.collect()
    return redirect(url_for('login'))

#Login page
@app.route("/login", methods=["GET", "POST"])
def login():
    #Need to do this to run on local:
    #export DATABASE_URL=postgres://opimlbnkhudqpv:e2c778406ab743a2bcdef8ce2c07544ba66dc50a75c241e4929215b1b2198f83@ec2-107-21-108-204.compute-1.amazonaws.com:5432/df9g9j9vm0bu32
    url = urlparse.urlparse(os.environ['DATABASE_URL'])

    error= None
    success= None

    if request.method== 'POST':
        session.pop('user', None)

        #Connect to database on heroku
        login_conn= psycopg2.connect(database=url.path[1:],
                                    user=url.username,
                                    password=url.password,
                                    host=url.hostname,
                                    port=url.port)

        login_conn.autocommit= True
        login_cursor = login_conn.cursor()

        #Main login fucntion here
        if 'password' in request.form:
            #Check password
            login_cursor.execute("SELECT id, password FROM users WHERE username = '{username}'".format(username= thwart(request.form['username'])))
            
            response = login_cursor.fetchall()
            if len(response)== 0:
                error = 'Incorrect Username/Password'
            else:
                if sha256_crypt.verify(request.form['password'], response[0][1])== True:
                    session['logged_in'] = True
                    session['user']= request.form['username']
                    login_cursor.close()
                    login_conn.close()
                    gc.collect()
                    return redirect(url_for('ticklist', user = '{a}_{b}'.format(a = thwart(session['user']),
                                                                                b = response[0][0])))

                else:
                    error= 'Incorrect Username/Password'

        #Creates a new user
        elif 'new_username' in request.form:
            new_username= request.form['new_username']
            if ' ' in new_username:
                error= 'Please enter a username without spaces'
                return render_template('login.html', error= error)

            new_password= sha256_crypt.encrypt(str(request.form['new_password']))
            new_email= request.form['new_email']

            #Create new account
            login_cursor.execute('''SELECT username FROM users where username= '{username}';'''.format(username= thwart(new_username)))
            existing_username= login_cursor.fetchall()
            login_cursor.execute('''SELECT email FROM users where email= '{email}';'''.format(email= thwart(new_email)))
            existing_email= login_cursor.fetchall()

            if len(existing_username)!= 0 or len(existing_email)!= 0:
                error= 'Account already exists!'
                return render_template('login.html', error= error)

            login_cursor.execute('''INSERT INTO users (username, password, email) 
                                    VALUES ('{username}', '{password}', '{email}')'''.format(username= thwart(new_username),
                                                                                             password= thwart(new_password),
                                                                                             email= thwart(new_email)))
            success= 'Account Created!'

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
            print 'OTHER'
            print request.form

    return render_template('login.html', error= error, success= success)

# Main page
@app.route("/", methods=["GET", "POST"])
#Comment in to require password
@login_required
def home():
    # get a connection, if a connect cannot be made an exception will be raised here
    url = urlparse.urlparse(os.environ['DATABASE_URL'])
    conn= psycopg2.connect(database=url.path[1:],
                            user=url.username,
                            password=url.password,
                            host=url.hostname,
                            port=url.port)

    conn.autocommit = True

    # conn.cursor will return a cursor object, you can use this cursor to perform queries
    cursor = conn.cursor()

    return render_template("home_page.html", username = thwart(session['user']), user_url = thwart(session['user']), main_page = 'Welcome')


#Ticklist page
@app.route("/ticklist/<user>", methods=["GET", "POST"])
@login_required
def ticklist(user):
    # get a connection, if a connect cannot be made an exception will be raised here
    url = urlparse.urlparse(os.environ['DATABASE_URL'])
    conn= psycopg2.connect(database=url.path[1:],
                            user=url.username,
                            password=url.password,
                            host=url.hostname,
                            port=url.port)

    conn.autocommit = True

    current_user = thwart(session['user'])
    user_id = user.split('_')[-1]

    # conn.cursor will return a cursor object, you can use this cursor to perform queries
    cursor = conn.cursor()

    cursor.execute('SELECT ticks.log_date, climbs.name, crags.sector, crags.name, ticks.suggested_grade, ticks.comment FROM ticks INNER JOIN users ON ticks.user_id = users.id INNER JOIN climbs ON ticks.climb_id = climbs.id INNER JOIN crags ON climbs.crag = crags.id WHERE users.id = {};'.format(user_id))

    ticks = cursor.fetchall()

    #------------------------------------------
    #Ticklist table creation
    ticklist_columns = [desc[0] for desc in cursor.description]
    print ticklist_columns

    
    table= '<thead><tr>'
    for header in ticklist_columns:
        table += '<th>{header}</th>'.format(header= header.replace('_',' ').title())

    table += '</tr></thead><tbody>'

    for row in ticks:
        for num, item in enumerate(row):
            if num == ticklist_columns.index('suggested_grade'):
                table += '<td>V{a}</td>'.format(a = item)
            else:
                table += '<td>{a}</td>'.format(a = item)
    table += '</tr></body>'

    #     table += '<tr>'
    #     oid= row[1]
    #     row= row[0:1] + row[2:]
    #     for num, item in enumerate(row):
    #         if num == 0:
    #             link= '{a}_{b}'.format(a= item.replace(' ','$$$'),
    #                                    b= oid)
    #             table += '<td><a href= /{a}>{b}</a></td>'.format(a= link,
    #                                                              b= item)
    #         elif num == 1:
    #             table += '<td>V{a}</td>'.format(a= item)
    #         else:
    #             table += '<td>{a}</td>'.format(a= item)

    # table += '</tr></body>'
    #------------------------------------------

    return render_template("ticklist_template.html", username = current_user, user_url = current_user, main_page = Markup(table))

    #Get a list of sectors and crags
    # cursor.execute('SELECT id, name, sector FROM crags;')
#     sectors_crags= []
#     for place in cursor.fetchall():
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

#             cursor.execute("SELECT * FROM boulders;")
#             boulders= cursor.fetchall()
#             for boulder in boulders:
#                 if boulder[1].lower()== climb.lower() and boulder[7].lower()== sector.lower():
#                     existing_climb= boulder[1]
#                     existing_lat= boulder[3]
#                     existing_lon= boulder[4]
#                     existing_sector= boulder[7]
#                     existing_crag= boulder[8]
            

#             if 'existing_climb' in locals():
#                 cursor.execute('''INSERT INTO boulders (username, climb, grade, latitude, longitude, sent_boo, privacy, sector, crag, comment, _date)
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
#                 cursor.execute('''INSERT INTO boulders (username, climb, grade, latitude, longitude, sent_boo, privacy, sector, crag, comment, _date)
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
#                         cursor.execute("SELECT DISTINCT on (climb, sector, crag) climb, oid, grade, latitude, longitude, sector, crag FROM boulders WHERE sector= '{a}';".format(a= thwart(sector)))
#                         all_boulders= cursor.fetchall()

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

#                     cursor.execute("SELECT DISTINCT on (climb, sector, crag) climb, oid, grade, latitude, longitude, sector, crag FROM boulders WHERE crag= '{a}';".format(a= thwart(crag)))
#                     all_boulders= cursor.fetchall()

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
#         cursor.execute("SELECT DISTINCT on (climb, sector, crag) climb, oid, grade, latitude, longitude, sector, crag FROM boulders;")

#         all_boulders = cursor.fetchall()

#     #------------------------------------------
#     #Ticklist table creation
#     ticklist_columns= [desc[0] for desc in cursor.description]
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
#     cursor.execute("SELECT crag, sector FROM boulders;")
#     boulders= cursor.fetchall()
#     autocomplete_list= []
#     for boulder_set in boulders:
#         if boulder_set[0] not in autocomplete_list:
#             autocomplete_list.append(boulder_set[0])
#         if boulder_set[1] not in autocomplete_list:
#             autocomplete_list.append(boulder_set[1])

#     cursor.close()
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

#         cursor = conn.cursor()

#         cursor.execute("SELECT climb, sector, crag, latitude, longitude FROM boulders WHERE oid = '{a}';".format(a= oid))
#         all_boulders= cursor.fetchall()[0]
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

#             cursor.execute('''INSERT INTO boulders (username, climb, grade, latitude, longitude, sent_boo, privacy, sector, crag, comment, _date)
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

#         cursor.execute("SELECT * FROM boulders WHERE climb = '{a}' AND sector = '{b}' AND crag = '{c}';".format(a= climb_name,
#                                                                                                                 b= sector,
#                                                                                                                 c= crag))

#         all_boulders = cursor.fetchall()

#         ticklist_columns= [desc[0] for desc in cursor.description]
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

#         cursor.close()
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

#     # conn.cursor will return a cursor object, you can use this cursor to perform queries
#     cursor = conn.cursor()

#     cursor.execute("SELECT sector, crag, latitude, longitude FROM boulders ORDER BY crag, sector;")

#     all_boulders = cursor.fetchall()

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

#     cursor.close()
#     conn.close()
#     gc.collect()
#     return render_template('error.html', error= 'Areas updated!')

# # #Error page
# # @app.route("/error", methods=["GET", "POST"])
# # @login_required
# # def error_page():

if __name__ == "__main__":
    app.run()
