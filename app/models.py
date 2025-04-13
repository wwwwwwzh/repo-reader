from . import db
from sqlalchemy.dialects.postgresql import JSON

class Repository(db.Model):
    """Repository model for storing repository information"""
    __tablename__ = 'repositories'
    
    id = db.Column(db.String(64), primary_key=True)  # Git commit hash
    url = db.Column(db.String(512), unique=True)
    entry_points = db.Column(JSON)  # List of entry function IDs
    parsed_at = db.Column(db.DateTime)
    
    # Relationships
    functions = db.relationship('Function', backref='repository', lazy='dynamic',
                               cascade='all, delete-orphan')

class Function(db.Model):
    """Function model for storing function information"""
    __tablename__ = 'functions'
    
    id = db.Column(db.String(128), primary_key=True)  # Composite ID: repo_hash:function_id
    repo_id = db.Column(db.String(64), db.ForeignKey('repositories.id', ondelete='CASCADE'))
    name = db.Column(db.String(128))  # Short name
    full_name = db.Column(db.String(512))  # Full qualified name
    file_path = db.Column(db.String(512))  # Path to the source file
    lineno = db.Column(db.Integer)  # Start line
    end_lineno = db.Column(db.Integer)  # End line
    is_entry = db.Column(db.Boolean, default=False)  # Whether this is an entry point
    class_name = db.Column(db.String(128), nullable=True)  # Class name if method
    module_name = db.Column(db.String(256))  # Module name
    
    # Relationships
    segments = db.relationship('Segment', 
                          foreign_keys='Segment.function_id',  # Specify which foreign key to use
                          backref=db.backref('function', lazy=True),
                          lazy='dynamic',
                          cascade='all, delete-orphan')
    callers = db.relationship('FunctionCall', 
                             foreign_keys='FunctionCall.callee_id',
                             backref=db.backref('callee', lazy=True),
                             lazy='dynamic',
                             cascade='all, delete-orphan')
    callees = db.relationship('FunctionCall', 
                             foreign_keys='FunctionCall.caller_id',
                             backref=db.backref('caller', lazy=True),
                             lazy='dynamic',
                             cascade='all, delete-orphan')

class Segment(db.Model):
    """Segment model for storing function segments (code, comments, calls)"""
    __tablename__ = 'segments'
    
    id = db.Column(db.String(256), primary_key=True)  # Composite ID: function_id:segment_index
    function_id = db.Column(db.String(128), db.ForeignKey('functions.id', ondelete='CASCADE'))
    type = db.Column(db.String(32))  # Segment type: code, comment, call
    content = db.Column(db.Text)  # Text content of the segment
    lineno = db.Column(db.Integer)  # Line number
    end_lineno = db.Column(db.Integer, nullable=True)  # End line number (for calls)
    index = db.Column(db.Integer)  # Index in the function for ordering
    
    # For call segments
    target_id = db.Column(db.String(128), db.ForeignKey('functions.id', ondelete='SET NULL'), 
                         nullable=True)  # Called function ID
    
    # Relationship to the target function for call segments
    target = db.relationship('Function', 
                        foreign_keys='Segment.target_id',  # Specify which foreign key to use
                        backref=db.backref('incoming_calls', lazy='dynamic'))
    
    # Additional metadata
    segment_data = db.Column(JSON, nullable=True)  # Additional information about the segment

class FunctionCall(db.Model):
    """Junction table for many-to-many relationship between caller and callee functions"""
    __tablename__ = 'function_calls'
    
    # Composite primary key
    caller_id = db.Column(db.String(128), db.ForeignKey('functions.id', ondelete='CASCADE'), 
                         primary_key=True)
    callee_id = db.Column(db.String(128), db.ForeignKey('functions.id', ondelete='CASCADE'),
                         primary_key=True)
    
    # Call instances might appear in multiple places
    # Store count of how many times the caller calls the callee
    call_count = db.Column(db.Integer, default=1)
    
    # We can add metadata about the call relationship if needed
    call_data = db.Column(JSON, nullable=True)