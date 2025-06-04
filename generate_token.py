#!/usr/bin/env python3
"""
Token Generator for Temperature Monitor API

This script generates a new secure bearer token and saves it to the .env file.
Run this script when you need to reset or create a new API token.
"""

import secrets
import os
import sys

def generate_token():
    """Generate a new bearer token and save it to .env file"""
    # Generate a secure random token
    new_token = secrets.token_hex(32)  # 64 character hex string
    
    # Check if .env file exists
    env_exists = os.path.isfile('.env')
    
    try:
        # Read existing .env content if it exists
        env_content = []
        if env_exists:
            with open('.env', 'r') as env_file:
                env_content = env_file.readlines()
        
        # Update or add the BEARER_TOKEN line
        token_line_found = False
        for i, line in enumerate(env_content):
            if line.startswith('BEARER_TOKEN='):
                env_content[i] = f'BEARER_TOKEN={new_token}\n'
                token_line_found = True
                break
        
        if not token_line_found:
            env_content.append(f'BEARER_TOKEN={new_token}\n')
        
        # Write back to .env file
        with open('.env', 'w') as env_file:
            env_file.writelines(env_content)
        
        print(f"New bearer token generated successfully: {new_token}")
        print("Token has been saved to .env file")
        print("\nTo use this token with curl:")
        print(f'curl -H "Authorization: Bearer {new_token}" http://your-server:8080/api/temp')
        
        return True
    except Exception as e:
        print(f"Error: Failed to save token to .env file: {e}", file=sys.stderr)
        print(f"\nYour generated token is: {new_token}")
        print("Please manually add this to your .env file as: BEARER_TOKEN=<token>")
        return False

if __name__ == "__main__":
    generate_token() 