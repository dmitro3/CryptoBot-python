import pymysql

# ssh_host = '203.161.62.119'
# ssh_username = 'root'
# ssh_password = 'r9RPK5Q2x4GBm1zc6v'

sql_hostname = '203.161.62.119'
sql_username = 'remoteuser'
sql_password = 'password'
sql_db = 'bot'
# Connect to the database
connection = pymysql.connect(host=sql_hostname,
                             user=sql_username,
                             password=sql_password,
                             database=sql_db,
                             cursorclass=pymysql.cursors.DictCursor)

def create_tables():
    with connection:
        with connection.cursor() as cursor:
            # Create tables or perform other operations
            sql = "CREATE TABLE IF NOT EXISTS `users` (`user_id` BIGINT PRIMARY KEY, `private_key` VARCHAR(255), `public_address` VARCHAR(255))"
            cursor.execute(sql)

            sql = "CREATE TABLE IF NOT EXISTS `deployed_bots` (`user_id` BIGINT, `bot_type` VARCHAR(50), `contract_address` VARCHAR(50), `balance` FLOAT, FOREIGN KEY (`user_id`) REFERENCES `users`(`user_id`))"
            cursor.execute(sql)

            connection.commit()
    connection.close()

def insert_user(user_id, private_key, public_address):
    with connection.cursor() as cursor:
        sql = """
        INSERT INTO `users` (`user_id`, `private_key`, `public_address`)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
        `private_key` = VALUES(`private_key`),
        `public_address` = VALUES(`public_address`)
        """
        cursor.execute(sql, (user_id, private_key, public_address))
    connection.commit()


def get_deployed_bots(user_id):
    with connection.cursor() as cursor:
        sql = "SELECT `bot_type`, `contract_address` FROM `deployed_bots` WHERE `user_id` = %s"
        cursor.execute(sql, (user_id,))
        deployed_bots = {}
        for row in cursor.fetchall():
            deployed_bots[row['bot_type']] = row['contract_address']
        return deployed_bots

def get_bot_fees():
    with connection.cursor() as cursor:
        sql = "SELECT * FROM `bot_fees`"
        cursor.execute(sql)
        fees = {}
        for row in cursor.fetchall():
            fees[row['bot_type']] = row['fee']
        return fees

def insert_deployed_bot(user_id, bot_type, contract_address):
    with connection.cursor() as cursor:
        sql = "INSERT INTO `deployed_bots` (`user_id`, `bot_type`, `contract_address`) VALUES (%s, %s, %s)"
        cursor.execute(sql, (user_id, bot_type, contract_address))
    connection.commit()




# def save_transaction(user_id, deployed_bot_id, tx, w3):
#     with connection:
#         with connection.cursor() as cursor:
#             sql = """
#                 INSERT INTO transactions (
#                     user_id, deployed_bot_id, tx_hash, block_number, from_address, to_address,
#                     value, gas_price, gas_used, timestamp
#                 )
#                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#             """
#             values = (
#                 user_id,
#                 deployed_bot_id,
#                 tx.hash.hex(),
#                 tx.blockNumber,
#                 tx['from'],
#                 tx.to,
#                 w3.fromWei(tx.value, 'ether'),
#                 tx.gasPrice,
#                 tx.gas,
#                 datetime.datetime.utcfromtimestamp(tx.timestamp)
#             )
#             cursor.execute(sql, values)
#             connection.commit()

