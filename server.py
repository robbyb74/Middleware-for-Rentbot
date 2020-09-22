import os
import json
import sqlite3

from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin

from celery import Celery

from facebook_template_lib import *
from df_response_lib import *


app = Flask(__name__)

app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'

celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)


fb = facebook_response()

ff_response = fulfillment_response()

# TODO implement address validation using AIzaSyDFmOGw4QKLuV8KsQwQoOP9lVuD9ZQGmsY key


@celery.task
def store_in_db(data):
    conn = sqlite3.connect('apartments.db')
    cursor = conn.cursor()

    cursor.execute('INSERT INTO apartments(address,size_apartments,price,date,pets,title,img) VALUES(?, ?, ?, ?, ?, ?, ?)', (
        data['address'],
        data['size_apartments'],
        data['price'],
        data['date'],
        data['pets'],
        data['title'],
        data['img']
    ))

    conn.commit()

    if conn:
        conn.close()

    if cursor:
        conn.close()


def check_db(address):
    conn = sqlite3.connect('apartments.db')
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM apartments WHERE address = ?', (
        address,
    ))

    status = False

    if cursor.fetchone() is None:
        status = True

    print('STATUS:', status)

    return status


def store_data(data):
    context_params = data['queryResult']['outputContexts'][0]

    if context_params:
        size_apartments = context_params['parameters'].get('size_apartments.original')
        date = context_params['parameters'].get('date_available')
        address = '{}, {}'.format(context_params['parameters'].get('landlord_address'),
                                  context_params['parameters'].get('landlord_city'))
        price = context_params['parameters'].get('landlord_price')
        pets = context_params['parameters'].get('pets')
        img = context_params['parameters'].get('img')
        title = context_params['parameters'].get('title')

        if pets == 'yes':
            pets = True
        else:
            pets = False

        print('GOT DATA', pets)

        apartment_data = {
            'address': address,
            'size_apartments': size_apartments,
            'price': price,
            'date': date,
            'pets': pets,
            'img': img,
            'title': title
        }

        print(apartment_data)

        status = check_db(address)

        if status is False:
            return {
                'fulfillmentText': 'That apartments already exists in our database, try to change your parameters'
            }

        store_in_db.apply_async(args=[apartment_data])

        main_msg = 'Your data is: {address}; {size_apartments}; {price}; {date}; {pets}'.format(
                address=address,
                size_apartments=size_apartments,
                price=price,
                date=date,
                pets=pets
            )

        # ff_msgs = {'fulfillment_messages':[
        #     {'text': {'text': ['COOL!']},
        #      'platform': 'FACEBOOK'},
        #     {'text': {'text': ['Your data is: {address}; {size_apartments}; {price}; {date}; {pets}'.format(
        #         address=address,
        #         size_apartments=size_apartments,
        #         price=price,
        #         date=date,
        #         pets=pets
        #     )]},
        #      'platform': 'FACEBOOK'}
        # ]}

        ff_text = ff_response.fulfillment_text(main_msg)

        ff_msgs = ff_response.fulfillment_messages(fb.text_response(['COOL', main_msg]))

        print(ff_msgs)

        response = ff_response.main_response(fulfillment_text=ff_text,
                                             fulfillment_messages=ff_msgs)

        return response


def validate_date(data):
    return {
        'fulfillmentText': ['thanks', 'hello']
    }


def find_results(data):
    context_params = data['queryResult']['outputContexts'][0]

    if context_params:
        size_apartments = context_params['parameters'].get('size-apartment-user.original')
        date = context_params['parameters'].get('date')
        # address = '{}, {}'.format(context_params['parameters'].get('landlord_address'),
        #                           context_params['parameters'].get('landlord_city'))
        price = context_params['parameters'].get('price')
        pets = context_params['parameters'].get('pets')

        if pets == 'yes':
            pets = True
        else:
            pets = False

        print('DATA YEEEE')

        conn = sqlite3.connect('apartments.db')
        cursor = conn.cursor()

        cursor.execute('''SELECT * FROM apartments WHERE size_apartments = ? AND date = ? AND pets = ? AND
            price = ?''', (
            size_apartments,
            date,
            pets,
            float(price)
        ))

        res = cursor.fetchall()

        if conn:
            conn.close()

        if cursor:
            conn.close()

        if res:
            cards = []

            # cards += fb.text_response(['That\'s what I found for you!'])

            for apartment in res:
                cards.append(
                    {
                        "card": {
                            "title": "{} size of {}".format(apartment[-2], apartment[2]),
                            "subtitle": apartment[1],
                            "imageUri": apartment[-1],
                            "buttons": [
                                {
                                    "text": "Book this apartments",
                                    "postback": "https://cdn.vox-cdn.com/thumbor/mwdkCtzfXICFeiC1UieFdpfNoL0=/0x0:3600x2754/1200x800/filters:focal(1512x1089:2088x1665)/cdn.vox-cdn.com/uploads/chorus_image/image/64920979/395_Detroit_St.25_forprintuse.0.jpg"
                                }
                            ]
                        }
                    }
                )

            print(cards)

            ff_text = ff_response.fulfillment_text('That\'s what I found for you!')

            ff_msgs = ff_response.fulfillment_messages(cards)

            print(ff_msgs)

            response = ff_response.main_response(fulfillment_text=ff_text,
                                                 fulfillment_messages=ff_msgs)

            return response
        else:
            return ff_response.main_response(
                fulfillment_text=ff_response.fulfillment_text('Sorry, but I didn\'t find results based on your query'))
    return ff_response.main_response(
        fulfillment_text=ff_response.fulfillment_text('Sorry, but I didn\'t find results based on your query'))


def extract_image(data):
    source = data['originalDetectIntentRequest']['payload']['data']['message']['attachments'][0]

    if source.get('type') == 'image':
        for index, context in enumerate(data['queryResult']['outputContexts']):
            if 'parameters' in context.keys():
                data['queryResult']['outputContexts'][index]['parameters']['img'] = source['payload'].get('url')

        fb_messages = fb.text_response(['I think that image will looks cool :)',
                                        'Choose or paste apartment\'s city'])

        ff_quickreplie = fb.quick_replies('Popular cities', ['Paris', 'Berlin', 'London', 'Kiev'])

        fb_messages.append(ff_quickreplie)

        ff_msgs = ff_response.fulfillment_messages(fb_messages)

        ff_text = ff_response.fulfillment_text('I think that image will looks cool :)')

        response = ff_response.main_response(fulfillment_text=ff_text,
                                             fulfillment_messages=ff_msgs,
                                             output_contexts={'output_contexts': data['queryResult']['outputContexts']})

        return response
    else:
        return ff_response.main_response(
            fulfillment_text=ff_response.fulfillment_text('Sorry, but that\'s not an image, could you upload another file please'),
        output_contexts={'output_contexts': data['queryResult']['outputContexts']})



@app.route("/dialogflow-connect", methods=['POST'])
def process_message():
    data = request.data.decode()

    print(data)

    data = json.loads(data)

    if data['queryResult']['intent'].get('displayName') == 'landlord-pets':
        response = store_data(data)
    elif data['queryResult']['intent'].get('displayName') == 'landlord-date-available':
        response = validate_date(data)
    elif data['queryResult']['intent'].get('displayName') == 'user-pets-initial':
        response = find_results(data)
    elif data['queryResult']['intent'].get('displayName') == 'landlord-img':
        response = extract_image(data)
    else:
        response = {'fulfillmentText': 'Sorry, could you repeat',
                    'outputContexts': data['queryResult']['outputContexts']}

    return jsonify(response)

if __name__ == '__main__':
    app.run(threaded=True, host='0.0.0.0', port=8000)