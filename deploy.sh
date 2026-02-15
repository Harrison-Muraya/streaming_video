#!/bin/bash

echo "🚀 Starting deployment..."

# Navigate to project directory
cd /var/www/streaming_video

# Pull latest code
echo "📥 Pulling latest code..."
git pull origin main

# Activate virtual environment
source venv/bin/activate

# Update dependencies
echo "📦 Updating dependencies..."
pip install -r requirements.txt --upgrade

# Run migrations (uncomment if you use Alembic)
# echo "🗄️  Running database migrations..."
# alembic upgrade head

# Set proper permissions
echo "🔐 Setting permissions..."
sudo chown -R www-data:www-data /var/www/streaming_video
sudo chmod -R 755 /var/www/streaming_video
sudo chmod 644 /var/www/streaming_video/.env

# Restart services
echo "🔄 Restarting services..."
sudo systemctl restart streaming_video
sudo systemctl restart celery

# Wait a moment for services to start
sleep 2

# Check status
echo "✅ Checking service status..."
sudo systemctl status streaming_video --no-pager | head -5
sudo systemctl status celery --no-pager | head -5

# Test the API
echo "🧪 Testing API..."
curl -s http://localhost:8000/health

echo ""
echo "✅ Deployment complete!"
echo "📊 View logs with: sudo journalctl -u streaming_video -f"
