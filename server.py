import os
import time
import tempfile
import json
import hashlib
import hmac
import logging
from dotenv import load_dotenv

from flask import Flask, request, render_template, jsonify
import requests
from requests import utils

load_dotenv()

VGS_USERNAME = os.getenv('VGS_USERNAME')
VGS_PASSWORD = os.getenv('VGS_PASSWORD')
VGS_VAULT_ID = os.getenv('VGS_VAULT_ID')
VGS_MERCHANT_ID = os.getenv('VGS_MERCHANT_ID')
SA_CLIENT_ID = os.getenv('SA_CLIENT_ID')
SA_CLIENT_SECRET = os.getenv('SA_CLIENT_SECRET')
PATH_TO_VGS_CA = os.getenv('PATH_TO_VGS_CA')
ADYEN_TOKEN = os.getenv('ADYEN_TOKEN')
ADYEN_MERCHANT_ACCOUNT = os.getenv('ADYEN_MERCHANT_ACCOUNT')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
APP_BASE_URL = os.getenv('APP_BASE_URL')

TIMSTAMP_DIFF_TOLERANCE = 60
DEBUG = True

app = Flask(__name__)

#----------Client -----------
# Payment Form
@app.route("/")
def payment_form():
    return render_template('index.html')

# Payment success page
@app.route('/payment-result')
def success_page():
    return render_template('payment-result.html')

#---------Server-----------
#MAIN
#Accept data from the client and enroll card into CMP
@app.route('/post', methods=['POST'])
def handle_client_request():
    if request.method == 'POST':
        print(f'\nClient Request:\n{json.dumps(request.json, indent=4)}')

        # Get Request Data
        transaction_amount = request.json['amount']
        card_holder = request.json['card_holder']
        card_cvc_token = request.json['card_cvc']
        card_number_token = request.json['card_number']
        card_exp_month = request.json['card_exp'].split(' / ')[0]
        card_exp_year = request.json['card_exp'].split(' / ')[1]

        #Generate Service Account Access Token:
        sa_token = generate_sa_token()

        #Enroll into CMP and Extract Card ID
        card_object = create_card_cmp(sa_token, card_number_token, card_exp_month, card_exp_year)
        card_id = card_object["data"]["id"]
        print(f'\nCard ID:\n"{card_id}"')

        #Give enough time for NT and AU to provision before attempting CMP requests and transactions
        print(f'\nSleeping for 15s to wait for NT and AU to provision...\n')
        time.sleep(15)

        try:
            #Get Updated Card (write custom logic for saving card object into DB here)
            card_object = get_card(sa_token, card_id)
        
            #Extract Network Token Number and Expiration
            network_token_number = card_object["included"][1]["attributes"]["network_token"]
            network_token_exp_month = card_object["included"][1]["attributes"]["exp_month"]
            network_token_exp_year = card_object["included"][1]["attributes"]["exp_year"]

            #Get Cryptogram Value and ECI once you are ready to process a CIT transaction.
            cryptogram_object = get_cryptogram(sa_token, card_id)
            cryptogram_value = cryptogram_object["data"]["attributes"]["cryptogram"]["value"]
            cryptogram_eci = cryptogram_object["data"]["attributes"]["cryptogram"]["eci"]

            #Print NT and Cryptogram related data
            print(f'\nNetwork Token (DPAN): "{network_token_number}"')
            print(f'Network Token Expiration Date: "{network_token_exp_month}/{network_token_exp_year}"')
            print(f'Cryptogram Value: "{cryptogram_value}"')
            print(f'Cryptogram ECI: "{cryptogram_eci}"')
        except Exception as e:
            print(f'Network Token failed to provision for the selected card')

        #Process with PAN + CVV  using Stripe or DPAN + Cryptogram using Adyen depending on transaction amount
        if float(transaction_amount) > 10:
            print('\nProcessing Transaction with Adyen Network Token Endpoing...')

            #Post Payment to Adyen:
            process_payment = post_to_adyen(network_token_number, network_token_exp_month, network_token_exp_year, cryptogram_value, cryptogram_eci)
            return {"status": process_payment['resultCode']}
       
        else:
            print('\nProcessing Transaction with Stripe using PAN and CVV aliases...')
            
            #Post to Stripe (Create Payment Method and Payment Intent with 3DS)
            payment_method = create_payment_method_stripe(card_number_token, card_cvc_token, card_exp_month, card_exp_year)
            intent = payment_intent_stripe(payment_method['id'])
            return {'payment_method': payment_method, 'payment_intent': intent} 
    else:
        return 'Error'

#Webhooks Endpoint. Accept event from CMP, verify signature and store event
@app.route('/cmp_events', methods=['POST'])
def handle_cmp_event():
    if request.method == 'POST':

        # Prettify and print the response
        formatted_json = json.dumps(request.json, indent=4)
        print('Headers:', request.headers)
        print('Webhook data:', formatted_json)

        return jsonify(request.json), 200


#---------Functions--------
#Generate Service Account Access Token
def generate_sa_token():
    url = "https://auth.verygoodsecurity.com/auth/realms/vgs/protocol/openid-connect/token"
    payload = {
        "client_id": SA_CLIENT_ID,
        "client_secret": SA_CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    response = requests.post(url, data=payload)
    sa_token = response.json()["access_token"]
    print(f'\nBeginning of the Access Token:\n"{sa_token[0:100]}..."')
    return sa_token


#Create card in CMP
def create_card_cmp(sa_token, card_number_token, card_exp_month, card_exp_year):
    url = "https://tntng36c6tl-3e59e6e4-c686-4ae3-921b-70a5c75ccc3f.sandbox.verygoodproxy.com/cards"
    headers = {
        "Authorization": f"Bearer {sa_token}",
        "Content-Type": "application/vnd.api+json" 
    }
    payload = { "data": { 
                        "attributes": 
                            {
                            "pan": card_number_token,
                            "exp_month": card_exp_month,
                            "exp_year": card_exp_year
                            } 
                        } 
               }
    response = requests.post(url, headers=headers, json=payload)

    #Prettify and return
    response_json = response.json()
    print(f'\nNew Card Object:\n{json.dumps(response_json, indent=4)}')
    return response_json


#Get Card from CMP
def get_card(sa_token, card_id):
    url = f"https://sandbox.vgsapi.com/cards/{card_id}"
    headers = {
        "Authorization": f"Bearer {sa_token}"
        }
    response = requests.get(url, headers=headers)

    #Prettify and return
    response_json = response.json()
    print(f'\nUpdated Card Object:\n{json.dumps(response_json, indent=4)}')
    return response_json


#Get Cryptogram
def get_cryptogram(sa_token, card_id):
    url = f"https://sandbox.vgsapi.com/cards/{card_id}/cryptogram"
    headers = {
        "Authorization": f"Bearer {sa_token}",
        "Content-Type": "application/vnd.api+json" 
        }
    payload = {
        "data": {
            "attributes": {
                "currency_code": "USD",
                "amount": 100.5,
                "transaction_type": "ECOM",
                "cryptogram_type": "TAVV"
            }
        }
    }
    response = requests.post(url, headers=headers, json=payload)

    #Prettify and return
    response_json = response.json()
    print(f'\nCryptogram Request Object:\n"{json.dumps(response_json, indent=4)}"')
    return response_json


# Post Payment to Adyen using NT
def post_to_adyen(network_token_number, network_token_exp_month, network_token_exp_year, cryptogram_value, cryptogram_eci):
    url = 'https://checkout-test.adyen.com/v69/payments'
    proxy = {'https': f'https://{VGS_USERNAME}:{VGS_PASSWORD}@{VGS_VAULT_ID}.sandbox.verygoodproxy.com:8443'}
    headers = {
        "X-API-key": ADYEN_TOKEN,
    }
    payload = {
        "amount": {
            "currency": "USD",
            "value": 1000
        },
        "reference": "12345678",
        "merchantAccount": "VGSAccount456ECOM",
        "mpiData": {
            "authenticationResponse": "Y",
            "directoryResponse": "Y",
            "eci": cryptogram_eci,
            "tokenAuthenticationVerificationValue": cryptogram_value
        },
        "paymentMethod": {
            "type": "networkToken",
            "brand": "visa",
            "number": network_token_number,
            "expiryMonth": int(network_token_exp_month),
            "expiryYear": int(str(20) + str(network_token_exp_year)),
            "holderName": "John Doe"
        },
        "shopperInteraction": "Ecommerce"
    }
    print('\nAdyent Payment Response: ')
    return post_request(url, headers, payload, proxy, use_json = True)


#Create Payment Method with Stripe
def create_payment_method_stripe(card_number_token, card_cvc_token, card_exp_month, card_exp_year):
    url = 'https://api.stripe.com/v1/payment_methods'
    proxy = {'https': f'https://{VGS_USERNAME}:{VGS_PASSWORD}@{VGS_VAULT_ID}.sandbox.verygoodproxy.com:8443'}
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Bearer {STRIPE_SECRET_KEY}'
    }
    payload = {
        'type':'card',
        'card[number]': card_number_token,
        'card[cvc]': card_cvc_token,
        'card[exp_month]': card_exp_month,
        'card[exp_year]': card_exp_year
    }
    print('\nStripe Payment Method: ')
    return post_request(url, headers, payload, proxy, use_json = False)


#Execute Payment Intent Stripe
def payment_intent_stripe(payment_id):
    url = 'https://api.stripe.com/v1/payment_intents'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Bearer {STRIPE_SECRET_KEY}'
    }
    payload = {
        'amount': 599,
        'currency': 'usd',
        'payment_method': payment_id,
        'confirm': 'true',
        'return_url': APP_BASE_URL + '/payment-result',
        'payment_method_options[card][request_three_d_secure]': 'requires_action',
    }
    print('\nStripe Payment Intent: ')
    return post_request(url, headers, payload, proxy = None, use_json = False)


#Make Post Request with Forward Proxy
def post_request(url, headers, payload, proxy, use_json):
    path_to_lib_ca = utils.DEFAULT_CA_BUNDLE_PATH
    with tempfile.NamedTemporaryFile() as ca_file:
        ca_file.write(read_file(PATH_TO_VGS_CA))
        ca_file.write(str.encode(os.linesep))
        ca_file.write(read_file(path_to_lib_ca))
        read_file(ca_file.name)
        try:
            if use_json == True: #If request goes to Stripe, we'll use form-encoded ("data") instead json - by default, use_json is True
                response = requests.post(url, headers=headers, json=payload, proxies=proxy, verify=ca_file.name)
            else:
                response = requests.post(url, headers=headers, data=payload, proxies=proxy, verify=ca_file.name)
            response.raise_for_status()

            #Prettify and return
            response_json = response.json()
            print(json.dumps(response_json, indent=4))
            return response_json
        
        except requests.exceptions.RequestException as e:
            print('post request failed: ', e)
            return 


# File Read Function needed for CA Bundle verification
def read_file(path):
    with open(path, mode='rb') as file:
        return file.read()


#Verify Webhook Signature
def check_signature(secret, signature, body):
    chunks = dict(p.split("=") for p in signature.split(","))
    if abs(int(chunks["t"]) - time.time()) > TIMSTAMP_DIFF_TOLERANCE:
        logging.warning("Timestamp mismatch")
        return False
    msg = chunks["t"].encode() + b"." + body
    mac = hmac.new(secret.encode("utf-8"), msg=msg, digestmod=hashlib.sha256)
    if mac.hexdigest() != chunks["v0"]:
        logging.warning("Signature mismatch")
        return False

    return True


if __name__ == '__main__':
    app.run(debug=DEBUG)




























'''

https://www.verygoodsecurity.com/docs/platform-insights/notifications#webhooks-signature


import hmac
import hashlib

# Your secret
secret = b"21efa60a1a296ffcdc931fcb3f160fd1"

# Example request data
timestamp = "1738803512"
body = '{"some":"json"}'  # Replace with the actual request body

# Construct the signed payload
signed_payload = f"{timestamp}.{body}".encode()

# Compute HMAC-SHA256 signature
computed_signature = hmac.new(secret, signed_payload, hashlib.sha256).hexdigest()

# Signature received in the header
received_signature = "c038a899b88e4cea9e96de5a3a4fdaa9062e5887d268a5ce463ccb2a67078377"

# Check if the signatures match
if computed_signature == received_signature:
    print("✅ Signature is valid!")
else:
    print("❌ Signature is invalid!")
    print(f"Computed: {computed_signature}")


'''
