"""
Database models and initialization
"""
import sqlite3
import json
from datetime import datetime
from .config import DB_PATH

def init_db():
    """Initialize database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Jobs table
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL,
            video_filename TEXT,
            template TEXT,
            aspect_ratio TEXT,
            output_path TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            error_message TEXT,
            metadata TEXT
        )
    ''')
    
    # Logs table
    c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            level TEXT NOT NULL,
            job_id TEXT,
            message TEXT NOT NULL,
            details TEXT
        )
    ''')
    
    # Queue table
    c.execute('''
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            priority INTEGER DEFAULT 0,
            added_at TEXT NOT NULL,
            processing BOOLEAN DEFAULT 0
        )
    ''')
    
    # Store sync table (placeholder for future)
    c.execute('''
        CREATE TABLE IF NOT EXISTS store_sync (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            sync_status TEXT,
            last_sync TEXT,
            metadata TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def create_job(job_id, video_filename, template, aspect_ratio='9:16', metadata=None):
    """Create a new job"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''
        INSERT INTO jobs (job_id, status, video_filename, template, aspect_ratio, created_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (job_id, 'queued', video_filename, template, aspect_ratio, 
          datetime.utcnow().isoformat(), json.dumps(metadata or {})))
    
    # Add to queue
    c.execute('''
        INSERT INTO queue (job_id, added_at)
        VALUES (?, ?)
    ''', (job_id, datetime.utcnow().isoformat()))
    
    conn.commit()
    conn.close()
    
    log_event('info', job_id, f'Job created: {template} template, {aspect_ratio}')
    return job_id

def update_job_status(job_id, status, output_path=None, error_message=None):
    """Update job status"""
    conn = get_db()
    c = conn.cursor()
    
    updates = ['status = ?']
    params = [status]
    
    if status == 'processing':
        updates.append('started_at = ?')
        params.append(datetime.utcnow().isoformat())
    elif status in ['completed', 'failed']:
        updates.append('completed_at = ?')
        params.append(datetime.utcnow().isoformat())
    
    if output_path:
        updates.append('output_path = ?')
        params.append(output_path)
    
    if error_message:
        updates.append('error_message = ?')
        params.append(error_message)
    
    params.append(job_id)
    
    c.execute(f'''
        UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?
    ''', params)
    
    conn.commit()
    conn.close()
    
    log_event('info', job_id, f'Status updated: {status}')

def get_job(job_id):
    """Get job by ID"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_recent_jobs(limit=20):
    """Get recent jobs"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def log_event(level, job_id, message, details=None):
    """Log an event"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO logs (timestamp, level, job_id, message, details)
        VALUES (?, ?, ?, ?, ?)
    ''', (datetime.utcnow().isoformat(), level, job_id, message, json.dumps(details) if details else None))
    conn.commit()
    conn.close()

def get_recent_logs(limit=50):
    """Get recent logs"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_next_queued_job():
    """Get next job from queue"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT q.job_id FROM queue q
        JOIN jobs j ON q.job_id = j.job_id
        WHERE q.processing = 0 AND j.status = 'queued'
        ORDER BY q.priority DESC, q.added_at ASC
        LIMIT 1
    ''')
    row = c.fetchone()
    
    if row:
        job_id = row[0]
        # Mark as processing
        c.execute('UPDATE queue SET processing = 1 WHERE job_id = ?', (job_id,))
        conn.commit()
    
    conn.close()
    return row[0] if row else None

def remove_from_queue(job_id):
    """Remove job from queue"""
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM queue WHERE job_id = ?', (job_id,))
    conn.commit()
    conn.close()

# Initialize database on import
init_db()
