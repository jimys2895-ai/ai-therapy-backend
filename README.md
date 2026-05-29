# BizQuest Backend

A FastAPI backend with MongoDB for JWT authentication, subscription management, and role-based access control.

## Features

- 🔐 JWT Authentication (signup, login, refresh tokens)
- 👤 User Management with MongoDB
- �️ Role-based Access Control (Customer, Moderator, Admin, Super Admin)
- �💳 Subscription Plans (Free, Pro Monthly, Pro Yearly)
- 🎯 Credit-based System (free plan has daily limits, paid plans unlimited)
- 📊 MongoDB with Motor (async driver)

## User Types & Permissions

### Customer (Default)
- Can create business ideas
- Can subscribe to plans
- Can view own data
- Limited to subscription features

### Moderator
- All customer permissions
- Can moderate content
- Can view analytics
- Can access admin panel
- Has unlimited idea generations

### Admin
- All moderator permissions
- Can manage users (customers and moderators)
- Can create new users
- Can change user roles (except admin/super admin)
- Can activate/deactivate users

### Super Admin
- All admin permissions
- Can manage other admins
- Can create admin and super admin users
- Full system access

## Subscription Plans

### Free Plan
- €0/forever
- 2 idea generations per day
- Basic business insights
- Email support
- Access to community

### Pro Monthly
- €2/month
- Unlimited idea generations
- Advanced business insights
- Priority support
- Export ideas to PDF
- Market analysis reports

### Pro Yearly
- €12/year (€1/month)
- Everything in Pro Monthly
- 50% cost savings
- Only €12 billed annually

## Setup

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Setup**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **MongoDB Setup**
   - Install MongoDB locally or use MongoDB Atlas
   - Update DATABASE_URL in .env

4. **Initialize Database**
   ```bash
   python init_db.py
   ```

5. **Create Super Admin User**
   ```bash
   python create_super_admin.py
   ```

6. **Run the Server**
   ```bash
   uvicorn src.main:app --reload
   ```

## API Endpoints

### Authentication
- `POST /api/v1/signup` - Create new user account
- `POST /api/v1/login` - Login user (returns JWT tokens)
- `GET /api/v1/me` - Get current user info
- `GET /api/v1/permissions` - Get current user's permissions

### User Management (Admin/Moderator)
- `GET /api/v1/users` - Get all users (moderator+)
- `POST /api/v1/admin/create-user` - Create new user (admin+)
- `PUT /api/v1/admin/users/{user_id}/role` - Update user role (admin+)
- `PUT /api/v1/admin/users/{user_id}/status` - Activate/deactivate user (admin+)
- `GET /api/v1/admin/users/{user_id}` - Get user details (moderator+)

### Subscription
- `GET /api/v1/subscription/plans` - Get all available plans
- `POST /api/v1/subscription/subscribe/{plan_name}` - Subscribe to a plan
- `GET /api/v1/subscription/my-subscription` - Get user's current subscription

### Credit System

- Free plan users get 2 credits per day (resets daily)
- Pro plan users have unlimited credits
- Credits are automatically managed by the system

## Development

The API documentation is available at `http://localhost:8000/docs` when running locally.

## Project Structure

```
Backend/
├── src/
│   ├── api/
│   │   └── v1/
│   │       ├── users/
│   │       │   └── users.py
│   │       └── subscribe/
│   │           └── plans.py
│   ├── auth/
│   │   ├── dependencies.py
│   │   ├── jwt.py
│   │   └── utils.py
│   ├── models/
│   │   ├── users.py
│   │   └── plans.py
│   ├── config.py
│   ├── database.py
│   └── main.py
├── requirements.txt
├── init_db.py
└── .env.example
```
