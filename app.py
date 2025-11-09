import os
from flask import Flask, jsonify, request
from dotenv import load_dotenv
import structlog
from datetime import datetime
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError
from flask_swagger_ui import get_swaggerui_blueprint

load_dotenv()

from db import get_db, close_db
from logger_config import setup_logging
from errors import register_error_handlers, ApiError
from utils import MongoJSONProvider
from prometheus_flask_exporter import PrometheusMetrics


setup_logging()
app = Flask(__name__)

# Use our custom JSON provider
app.json_provider_class = MongoJSONProvider
app.json = app.json_provider_class(app)

register_error_handlers(app)
log = structlog.get_logger()

metrics = PrometheusMetrics(app)

SWAGGER_URL = '/docs'
API_URL = '/static/customer_service_openapi.yaml'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "Customer Service API Docs"
    }
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

@app.before_request
def before_request():
    # Bind correlation ID to logger context for this request
    correlation_id = request.headers.get('X-Correlation-Id')
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        path=request.path,
        method=request.method
    )
    log.info("request_started", request_body=request.get_json(silent=True))


@app.after_request
def after_request(response):
    log.info("request_finished", status_code=response.status_code)
    return response


# Close DB connection after each request
@app.teardown_appcontext
def teardown_db(exception):
    close_db(exception)


# --- Health Check ---
@app.route('/healthz', methods=['GET'])
def health_check():
    """Health probe for Kubernetes."""
    return jsonify({"status": "ok", "service": "customer-service"}), 200



@app.route('/v1/customers', methods=['POST'])
def create_customer():
    data = request.get_json()
    if not data or not 'name' in data or not 'email' in data or not 'phone' in data:
        raise ApiError("Name, email, and phone are required", 400, "BAD_REQUEST")

    db = get_db()

    new_customer_doc = {
        "name": data['name'],
        "email": data['email'],
        "phone": data['phone'],
        "addresses": [],
        "created_at": datetime.utcnow()
    }

    try:
        result = db.customers.insert_one(new_customer_doc)
        new_customer = db.customers.find_one({"_id": result.inserted_id})
        return jsonify(new_customer), 201

    except DuplicateKeyError:
        raise ApiError("Email or phone already exists. (Have you created unique indexes?)", 409, "CONFLICT")
    except Exception as e:
        raise ApiError(str(e), 500, "DATABASE_ERROR")


@app.route('/v1/customers', methods=['GET'])
def list_customers():
    # Supports pagination and filtering
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    email = request.args.get('email')
    offset = (page - 1) * limit

    db = get_db()
    query = {}
    if email:
        # Case-insensitive search
        query['email'] = {"$regex": email, "$options": "i"}

    customers = list(db.customers.find(query).skip(offset).limit(limit))

    return jsonify({
        "page": page,
        "limit": limit,
        "data": customers
    }), 200


@app.route('/v1/customers/<customer_id>', methods=['GET'])
def get_customer_by_id(customer_id):
    db = get_db()
    try:
        obj_id = ObjectId(customer_id)
    except InvalidId:
        raise ApiError("Invalid customer_id format", 400, "BAD_REQUEST")

    customer = db.customers.find_one({"_id": obj_id})
    if not customer:
        raise ApiError("Customer not found", 404, "NOT_FOUND")

    return jsonify(customer), 200



@app.route('/v1/customers/<customer_id>/addresses', methods=['POST'])
def create_address(customer_id):
    try:
        customer_obj_id = ObjectId(customer_id)
    except InvalidId:
        raise ApiError("Invalid customer_id format", 400, "BAD_REQUEST")

    data = request.get_json()
    if not data or not 'line1' in data or not 'city' in data or not 'pincode' in data:
        raise ApiError("line1, city, and pincode are required", 400, "BAD_REQUEST")

    db = get_db()

    new_address = {
        "_id": ObjectId(),
        "line1": data['line1'],
        "area": data.get('area'),
        "city": data['city'],
        "pincode": data['pincode'],
        "created_at": datetime.utcnow()
    }

    result = db.customers.update_one(
        {"_id": customer_obj_id},
        {"$push": {"addresses": new_address}}
    )

    if result.matched_count == 0:
        raise ApiError("Customer not found", 404, "NOT_FOUND")

    return jsonify(new_address), 201


@app.route('/v1/customers/<customer_id>/addresses', methods=['GET'])
def list_addresses_for_customer(customer_id):
    try:
        customer_obj_id = ObjectId(customer_id)
    except InvalidId:
        raise ApiError("Invalid customer_id format", 400, "BAD_REQUEST")

    db = get_db()
    customer = db.customers.find_one(
        {"_id": customer_obj_id},
        {"addresses": 1, "_id": 0}
    )

    if not customer:
        raise ApiError("Customer not found", 404, "NOT_FOUND")

    return jsonify(customer.get('addresses', [])), 200


@app.route('/v1/addresses/<address_id>', methods=['GET'])
def get_address_by_id(address_id):
    """Internal-facing endpoint for other services."""
    try:
        address_obj_id = ObjectId(address_id)
    except InvalidId:
        raise ApiError("Invalid address_id format", 400, "BAD_REQUEST")

    db = get_db()

    customer = db.customers.find_one(
        {"addresses._id": address_obj_id},
        {"_id": 0, "addresses.$": 1}
    )

    if not customer or 'addresses' not in customer or len(customer['addresses']) == 0:
        raise ApiError("Address not found", 404, "NOT_FOUND")

    return jsonify(customer['addresses'][0]), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8081)), debug=True)