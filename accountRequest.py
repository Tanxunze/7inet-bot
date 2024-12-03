import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime


def fetch_vps_list():
    base_url = "https://api.7inet.com.cn"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Referer': 'https://api.7inet.com.cn/'
    }

    # Step 1: Login Request
    login_url = f"{base_url}/user/oauth.do"
    login_params = {
        'code': '',
        'method': 'login.chk',
        'u': 'Mio',
        'p': '@7inet221811'
    }

    try:
        # Get login token
        login_response = requests.get(login_url, params=login_params, headers=headers)
        login_data = json.loads(login_response.text)

        if login_data.get('code') == 200 and 'token' in login_data:
            token = login_data['token']
            print(f"Successfully logged in with token: {token}")

            # Step 2: Get VPS instance list
            instance_url = f"{base_url}/user/instance_manager.page"
            instance_params = {
                'token': token,
                'showexpired': 'false'
            }

            instance_response = requests.get(instance_url, params=instance_params, headers=headers)

            # Parse HTML content
            soup = BeautifulSoup(instance_response.text, 'html.parser')

            # Extract table data
            instances = []
            table = soup.find('table')
            if table:
                # Print header
                header = ["ID", "Instance Name", "Status", "Start Time", "End Time", "Username", "Password"]
                print("\n{:<15} {:<15} {:<10} {:<25} {:<25} {:<20} {:<20}".format(*header))
                print("-" * 130)

                # Process rows
                rows = table.find_all('tr')[1:]  # Skip header row
                for row in rows:
                    cols = row.find_all(['td'])
                    if len(cols) >= 8:
                        instance = {
                            'id': cols[0].text.strip(),
                            'name': cols[1].find('span').text.strip(),
                            'status': cols[2].find('font').text.strip(),
                            'start_time': cols[3].text.strip(),
                            'end_time': cols[4].text.strip(),
                            'username': cols[5].find('span').text.strip(),
                            'password': cols[6].find('span').text.strip()
                        }
                        instances.append(instance)

                        # Print instance details
                        print("{:<15} {:<15} {:<10} {:<25} {:<25} {:<20} {:<20}".format(
                            instance['id'],
                            instance['name'],
                            instance['status'],
                            instance['start_time'],
                            instance['end_time'],
                            instance['username'],
                            instance['password']
                        ))

            # Save to text file
            current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            txt_filename = f"vps_instances_{current_time}.txt"
            with open(txt_filename, 'w', encoding='utf-8') as f:
                f.write("VPS Instances List\n")
                f.write("-" * 130 + "\n")
                f.write("{:<15} {:<15} {:<10} {:<25} {:<25} {:<20} {:<20}\n".format(*header))
                f.write("-" * 130 + "\n")
                for instance in instances:
                    f.write("{:<15} {:<15} {:<10} {:<25} {:<25} {:<20} {:<20}\n".format(
                        instance['id'],
                        instance['name'],
                        instance['status'],
                        instance['start_time'],
                        instance['end_time'],
                        instance['username'],
                        instance['password']
                    ))
            print(f"\nData saved to {txt_filename}")

        else:
            print("Failed to login")

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    fetch_vps_list()