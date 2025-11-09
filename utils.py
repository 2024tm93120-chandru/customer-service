import json
from bson import ObjectId
from datetime import datetime
from flask.json.provider import JSONProvider

class MongoJSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder to handle MongoDB BSON types.
    """
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super(MongoJSONEncoder, self).default(obj)

class MongoJSONProvider(JSONProvider):
    """
    Custom JSON provider for Flask to use our encoder.
    """
    def dumps(self, obj, **kwargs):
        return json.dumps(obj, **kwargs, cls=MongoJSONEncoder)

    def loads(self, s, **kwargs):
        return json.loads(s, **kwargs)