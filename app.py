import psycopg2
from psycopg2.extras import RealDictCursor  # ← ADD THIS
from flask import Flask, request, jsonify, render_template
from decimal import Decimal
from datetime import datetime  # ← ADD THIS

# --- Database Connection Configuration ---
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "Insurance Rating Software"
DB_USER = "postgres"
DB_PASS = "Aviators2025!!"

# --- Initialize the Flask App ---
app = Flask(__name__)

# --- Helper Function to Get DB Connection ---
def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )
    return conn

# --- Route for HTML page ---
@app.route("/")
def home():
    return render_template("index.html")

# --- FIXED: ZIP CODE LOOKUP ENDPOINT (Now uses PostgreSQL) ---
@app.route("/lookup/state_by_zip", methods=["POST"])
def lookup_state_by_zip():
    try:
        data = request.json
        zip_code = data.get("zip_code")
        print(f"DEBUG: Received zip_code: {zip_code}")  # Debug
        state = ""
        
        if zip_code and len(zip_code) == 5 and zip_code.isdigit():
            print(f"DEBUG: Valid zip format, looking up in database...")  # Debug
            conn = get_db_connection()  # Use PostgreSQL connection
            cur = conn.cursor()
            
            # PostgreSQL uses %s instead of ? for parameters
            sql = "SELECT state_code FROM zipcodes WHERE zip_code = %s"
            cur.execute(sql, (zip_code,))
            result = cur.fetchone()
            
            print(f"DEBUG: Query result: {result}")  # Debug
            
            if result:
                state = result[0]
                print(f"DEBUG: Found state: {state}")  # Debug
            else:
                print(f"DEBUG: No state found for zip: {zip_code}")  # Debug
            
            cur.close()
            conn.close()
        else:
            print(f"DEBUG: Invalid zip format")  # Debug
        
        return jsonify({"state": state})
    except Exception as e:
        print(f"Zip Lookup Error: {e}")
        import traceback
        traceback.print_exc()  # Print full error trace
        return jsonify({"error": str(e)}), 500
    
# --- VEHICLE BODY TYPE LOOKUP ENDPOINT ---
@app.route("/lookup/vehicle_body_types", methods=["POST"])
def lookup_vehicle_body_types():
    try:
        data = request.json
        vehicle_class = data.get("vehicle_class")
        
        print(f"DEBUG Vehicle Body Type Lookup - Class: {vehicle_class}")
        
        body_types = []
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT body_type 
            FROM vehicle_body_type_lookup
            WHERE vehicle_class = %s
            ORDER BY display_order;
        """
        cur.execute(sql, (vehicle_class,))
        results = cur.fetchall()
        
        for row in results:
            body_types.append(row[0])
        
        cur.close()
        conn.close()
        
        print(f"DEBUG Vehicle Body Type Lookup - Found {len(body_types)} body types")
        
        return jsonify({"body_types": body_types})
    except Exception as e:
        print(f"Vehicle Body Type Lookup Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    

# --- Territory Lookup ---
@app.route('/lookup/territory', methods=['POST'])
def lookup_territory():
    """
    Look up AL territory by zip code for Non Admitted rating
    """
    try:
        data = request.get_json()
        effective_date = data.get('effective_date')
        state_code = data.get('state_code')
        zipcode = data.get('zipcode')
        
        if not all([effective_date, state_code, zipcode]):
            return jsonify({
                'error': 'Missing required fields: effective_date, state_code, zipcode'
            }), 400
        
        query = """
            SELECT territory
            FROM ss_territory_lookup
            WHERE state_code = %s
              AND zipcode = %s
              AND effective_date <= %s
            ORDER BY effective_date DESC
            LIMIT 1
        """
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query, (state_code, zipcode, effective_date))
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result:
            return jsonify({
                'territory': result[0]
            })
        else:
            return jsonify({
                'territory': None,
                'message': 'No territory found for this zip code'
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# --- SS Radius Factor ---
@app.route('/rate/ss_radius_factor', methods=['POST'])
def get_ss_radius_factor():
    """
    Get Non Admitted weighted radius factor
    """
    print("=== SS RADIUS FACTOR CALLED ===")
    try:
        data = request.get_json()
        print(f"Received data: {data}")
        
        effective_date = data.get('effective_date')
        state_code = data.get('state_code')
        zipcode = data.get('zipcode')
        
        print(f"Effective date: {effective_date}")
        print(f"State code: {state_code}")
        print(f"Zipcode: {zipcode}")
        
        radius_0_50 = float(data.get('radius_0_50', 0))
        radius_51_200 = float(data.get('radius_51_200', 0))
        radius_201_500 = float(data.get('radius_201_500', 0))
        radius_501_plus = float(data.get('radius_501_plus', 0))
        
        print(f"Radius values: {radius_0_50}, {radius_51_200}, {radius_201_500}, {radius_501_plus}")
        
        if not all([effective_date, state_code, zipcode]):
            print("ERROR: Missing required fields")
            return jsonify({
                'error': 'Missing required fields: effective_date, state_code, zipcode'
            }), 400
        
        default_factors = {
            '0-50': 1.29,
            '51-200': 1.49,
            '201-500': 1.69,
            '501+': 1.89
        }
        
        print("Connecting to database...")
        conn = get_db_connection()
        cur = conn.cursor()
        
        territory_query = """
            SELECT territory
            FROM ss_territory_lookup
            WHERE state_code = %s
              AND zipcode = %s
              AND effective_date <= %s
            ORDER BY effective_date DESC
            LIMIT 1
        """
        
        print(f"Looking up territory with: {state_code}, {zipcode}, {effective_date}")
        cur.execute(territory_query, (state_code, zipcode, effective_date))
        territory_result = cur.fetchone()
        print(f"Territory result: {territory_result}")
        
        if not territory_result:
            print("No territory found, using defaults")
            cur.close()
            conn.close()
            territory = 'DEFAULT'
            factor_0_50 = default_factors['0-50']
            factor_51_200 = default_factors['51-200']
            factor_201_500 = default_factors['201-500']
            factor_501_plus = default_factors['501+']
        else:
            territory = territory_result[0]
            print(f"Territory found: {territory}")
            
            count_query = "SELECT COUNT(*) FROM ss_radius_factor WHERE state_code = %s AND territory = %s"
            cur.execute(count_query, (state_code, territory))
            count_result = cur.fetchone()
            print(f"Number of radius factor records for {state_code}/{territory}: {count_result[0]}")
            
            date_query = """
                SELECT MAX(effective_date) as max_date
                FROM ss_radius_factor
                WHERE state_code = %s
                  AND territory = %s
                  AND effective_date <= %s
            """
            
            cur.execute(date_query, (state_code, territory, effective_date))
            date_result = cur.fetchone()
            print(f"Max effective date: {date_result}")
            
            if date_result and date_result[0]:
                max_effective_date = date_result[0]
                
                radius_query = """
                    SELECT radius_category, factor
                    FROM ss_radius_factor
                    WHERE state_code = %s
                      AND territory = %s
                      AND effective_date = %s
                """
                
                cur.execute(radius_query, (state_code, territory, max_effective_date))
                radius_results = cur.fetchall()
                print(f"Radius results: {radius_results}")
                
                factors = {}
                for row in radius_results:
                    factors[row[0]] = float(row[1])
                
                factor_0_50 = factors.get('0-50', default_factors['0-50'])
                factor_51_200 = factors.get('51-200', default_factors['51-200'])
                factor_201_500 = factors.get('201-500', default_factors['201-500'])
                factor_501_plus = factors.get('501+', default_factors['501+'])
            else:
                print("No radius factors found, using defaults")
                factor_0_50 = default_factors['0-50']
                factor_51_200 = default_factors['51-200']
                factor_201_500 = default_factors['201-500']
                factor_501_plus = default_factors['501+']
        
        cur.close()
        conn.close()
        
        print(f"Factors being used: {factor_0_50}, {factor_51_200}, {factor_201_500}, {factor_501_plus}")
        
        weighted_factor = (
            (radius_0_50 / 100.0 * factor_0_50) +
            (radius_51_200 / 100.0 * factor_51_200) +
            (radius_201_500 / 100.0 * factor_201_500) +
            (radius_501_plus / 100.0 * factor_501_plus)
        )
        
        weighted_factor = round(weighted_factor, 4)
        
        print(f"Weighted factor calculated: {weighted_factor}")
        
        return jsonify({
            'state_code': state_code,
            'territory': territory,
            'weighted_factor': weighted_factor,
            'factors_used': {
                '0-50': factor_0_50,
                '51-200': factor_51_200,
                '201-500': factor_201_500,
                '501+': factor_501_plus
            },
            'percentages': {
                '0-50': radius_0_50,
                '51-200': radius_51_200,
                '201-500': radius_201_500,
                '501+': radius_501_plus
            }
        })
            
    except Exception as e:
        print(f"!!! EXCEPTION OCCURRED !!!")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
# --- SS (Non Admitted) MINIMUM PREMIUM ENDPOINT ---
@app.route("/rate/ss_minimum_premium", methods=["POST"])
def rate_ss_minimum_premium():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        radius_category = data.get("radius_category")
        vehicle_class = data.get("vehicle_class")
        al_limit = int(data.get("al_limit", 0))
        
        print(f"DEBUG SS Min Premium - Date: {policy_date}, State: {state_code}, Radius: {radius_category}, Class: {vehicle_class}, Limit: {al_limit}")
        
        minimum_premium = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT minimum_premium 
            FROM ss_minimum_premiums
            WHERE effective_date <= %s 
              AND state_code = %s
              AND radius_category = %s
              AND vehicle_class = %s
              AND al_limit = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, radius_category, vehicle_class, al_limit))
        result = cur.fetchone()
        
        if result:
            minimum_premium = result[0]
            print(f"DEBUG SS Min Premium - Found: {minimum_premium}")
        else:
            print(f"DEBUG SS Min Premium - No minimum found")
        
        cur.close()
        conn.close()
        
        return jsonify({"minimum_premium": str(minimum_premium)})
    except Exception as e:
        print(f"SS Minimum Premium Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- SS (Non Admitted) UMBI BASE RATE ENDPOINT ---
@app.route("/rate/ss_umbi", methods=["POST"])
def rate_ss_umbi():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS UMBI - Date: {policy_date}, State: {state_code}")
        
        base_rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate FROM ss_umbi_base_rates
            WHERE effective_date <= %s AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            base_rate = result[0]
            print(f"DEBUG SS UMBI - Found rate: {base_rate}")
        else:
            print(f"DEBUG SS UMBI - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"base_rate": str(base_rate)})
    except Exception as e:
        print(f"SS UMBI Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) UMBI ILF FACTOR ENDPOINT ---
@app.route("/rate/ss_umbi_ilf_factor", methods=["POST"])
def rate_ss_umbi_ilf_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS UMBI ILF Factor - Date: {policy_date}, State: {state_code}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_umbi_ilf_factor
            WHERE effective_date <= %s 
              AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS UMBI ILF Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS UMBI ILF Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS UMBI ILF Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500   

# --- SS (Non Admitted) UMBI BODY TYPE BUSINESS FACTOR ENDPOINT ---
@app.route("/rate/ss_umbi_btb_factor", methods=["POST"])
def rate_ss_umbi_btb_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        vehicle_class = data.get("vehicle_class")
        business_use_type = data.get("business_use_type")
        
        print(f"DEBUG SS UMBI BTB Factor - Date: {policy_date}, State: {state_code}, Body: {body_type}, Class: {vehicle_class}, Business: {business_use_type}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_umbi_btb_factor
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND vehicle_class = %s
              AND business_use_type = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, vehicle_class, business_use_type))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS UMBI BTB Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS UMBI BTB Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS UMBI BTB Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500 
    
# --- SS (Non Admitted) UMBI BODY TYPE BUSINESS CLASS TRAILER FACTOR ENDPOINT ---
@app.route("/rate/ss_umbi_btbct_factor", methods=["POST"])
def rate_ss_umbi_btbct_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        business_use_type = data.get("business_use_type")
        
        print(f"DEBUG SS UMBI BTBCT Factor - Date: {policy_date}, State: {state_code}, Body: {body_type}, Business: {business_use_type}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_umbi_btbct_factor
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND business_use_type = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, business_use_type))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS UMBI BTBCT Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS UMBI BTBCT Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS UMBI BTBCT Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- SS UMBI Radius Factor ---
@app.route('/rate/ss_umbi_radius_factor', methods=['POST'])
def get_ss_umbi_radius_factor():
    """
    Get Non Admitted UMBI weighted radius factor
    """
    print("=== SS UMBI RADIUS FACTOR CALLED ===")
    try:
        data = request.get_json()
        print(f"Received data: {data}")
        
        effective_date = data.get('effective_date')
        state_code = data.get('state_code')
        zipcode = data.get('zipcode')
        
        print(f"Effective date: {effective_date}")
        print(f"State code: {state_code}")
        print(f"Zipcode: {zipcode}")
        
        radius_0_50 = float(data.get('radius_0_50', 0))
        radius_51_200 = float(data.get('radius_51_200', 0))
        radius_201_500 = float(data.get('radius_201_500', 0))
        radius_501_plus = float(data.get('radius_501_plus', 0))
        
        print(f"Radius values: {radius_0_50}, {radius_51_200}, {radius_201_500}, {radius_501_plus}")
        
        if not all([effective_date, state_code, zipcode]):
            print("ERROR: Missing required fields")
            return jsonify({
                'error': 'Missing required fields: effective_date, state_code, zipcode'
            }), 400
        
        default_factors = {
            '0-50': 1.29,
            '51-200': 1.49,
            '201-500': 1.69,
            '501+': 1.89
        }
        
        print("Connecting to database...")
        conn = get_db_connection()
        cur = conn.cursor()
        
        territory_query = """
            SELECT territory
            FROM ss_territory_lookup
            WHERE state_code = %s
              AND zipcode = %s
              AND effective_date <= %s
            ORDER BY effective_date DESC
            LIMIT 1
        """
        
        print(f"Looking up territory with: {state_code}, {zipcode}, {effective_date}")
        cur.execute(territory_query, (state_code, zipcode, effective_date))
        territory_result = cur.fetchone()
        print(f"Territory result: {territory_result}")
        
        if not territory_result:
            print("No territory found, using defaults")
            cur.close()
            conn.close()
            territory = 'DEFAULT'
            factor_0_50 = default_factors['0-50']
            factor_51_200 = default_factors['51-200']
            factor_201_500 = default_factors['201-500']
            factor_501_plus = default_factors['501+']
        else:
            territory = territory_result[0]
            print(f"Territory found: {territory}")
            
            count_query = "SELECT COUNT(*) FROM ss_umbi_radius_factor WHERE state_code = %s AND territory = %s"
            cur.execute(count_query, (state_code, territory))
            count_result = cur.fetchone()
            print(f"Number of UMBI radius factor records for {state_code}/{territory}: {count_result[0]}")
            
            date_query = """
                SELECT MAX(effective_date) as max_date
                FROM ss_umbi_radius_factor
                WHERE state_code = %s
                  AND territory = %s
                  AND effective_date <= %s
            """
            
            cur.execute(date_query, (state_code, territory, effective_date))
            date_result = cur.fetchone()
            print(f"Max effective date: {date_result}")
            
            if date_result and date_result[0]:
                max_effective_date = date_result[0]
                
                radius_query = """
                    SELECT radius_category, factor
                    FROM ss_umbi_radius_factor
                    WHERE state_code = %s
                      AND territory = %s
                      AND effective_date = %s
                """
                
                cur.execute(radius_query, (state_code, territory, max_effective_date))
                radius_results = cur.fetchall()
                print(f"Radius results: {radius_results}")
                
                factors = {}
                for row in radius_results:
                    factors[row[0]] = float(row[1])
                
                factor_0_50 = factors.get('0-50', default_factors['0-50'])
                factor_51_200 = factors.get('51-200', default_factors['51-200'])
                factor_201_500 = factors.get('201-500', default_factors['201-500'])
                factor_501_plus = factors.get('501+', default_factors['501+'])
            else:
                print("No UMBI radius factors found, using defaults")
                factor_0_50 = default_factors['0-50']
                factor_51_200 = default_factors['51-200']
                factor_201_500 = default_factors['201-500']
                factor_501_plus = default_factors['501+']
        
        cur.close()
        conn.close()
        
        print(f"Factors being used: {factor_0_50}, {factor_51_200}, {factor_201_500}, {factor_501_plus}")
        
        weighted_factor = (
            (radius_0_50 / 100.0 * factor_0_50) +
            (radius_51_200 / 100.0 * factor_51_200) +
            (radius_201_500 / 100.0 * factor_201_500) +
            (radius_501_plus / 100.0 * factor_501_plus)
        )
        
        weighted_factor = round(weighted_factor, 4)
        
        print(f"Weighted factor calculated: {weighted_factor}")
        
        return jsonify({
            'state_code': state_code,
            'territory': territory,
            'weighted_factor': weighted_factor,
            'factors_used': {
                '0-50': factor_0_50,
                '51-200': factor_51_200,
                '201-500': factor_201_500,
                '501+': factor_501_plus
            },
            'percentages': {
                '0-50': radius_0_50,
                '51-200': radius_51_200,
                '201-500': radius_201_500,
                '501+': radius_501_plus
            }
        })
            
    except Exception as e:
        print(f"!!! EXCEPTION OCCURRED !!!")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# --- SS (Non Admitted) UMPD BASE RATE ENDPOINT ---
@app.route("/rate/ss_umpd", methods=["POST"])
def rate_ss_umpd():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS UMPD - Date: {policy_date}, State: {state_code}")
        
        base_rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate FROM ss_umpd_base_rates
            WHERE effective_date <= %s AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            base_rate = result[0]
            print(f"DEBUG SS UMPD - Found rate: {base_rate}")
        else:
            print(f"DEBUG SS UMPD - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"base_rate": str(base_rate)})
    except Exception as e:
        print(f"SS UMPD Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) UMPD ILF FACTOR ENDPOINT ---
@app.route("/rate/ss_umpd_ilf_factor", methods=["POST"])
def rate_ss_umpd_ilf_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS UMPD ILF Factor - Date: {policy_date}, State: {state_code}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_umpd_ilf_factor
            WHERE effective_date <= %s 
              AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS UMPD ILF Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS UMPD ILF Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS UMPD ILF Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) UMPD BODY TYPE BUSINESS FACTOR ENDPOINT ---
@app.route("/rate/ss_umpd_btb_factor", methods=["POST"])
def rate_ss_umpd_btb_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        vehicle_class = data.get("vehicle_class")
        business_use_type = data.get("business_use_type")
        
        print(f"DEBUG SS UMPD BTB Factor - Date: {policy_date}, State: {state_code}, Body: {body_type}, Class: {vehicle_class}, Business: {business_use_type}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_umpd_btb_factor
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND vehicle_class = %s
              AND business_use_type = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, vehicle_class, business_use_type))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS UMPD BTB Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS UMPD BTB Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS UMPD BTB Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) UMPD BODY TYPE BUSINESS CLASS TRAILER FACTOR ENDPOINT ---
@app.route("/rate/ss_umpd_btbct_factor", methods=["POST"])
def rate_ss_umpd_btbct_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        business_use_type = data.get("business_use_type")
        
        print(f"DEBUG SS UMPD BTBCT Factor - Date: {policy_date}, State: {state_code}, Body: {body_type}, Business: {business_use_type}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_umpd_btbct_factor
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND business_use_type = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, business_use_type))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS UMPD BTBCT Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS UMPD BTBCT Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS UMPD BTBCT Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS UMPD Radius Factor ---
@app.route('/rate/ss_umpd_radius_factor', methods=['POST'])
def get_ss_umpd_radius_factor():
    """
    Get Non Admitted UMPD weighted radius factor
    """
    print("=== SS UMPD RADIUS FACTOR CALLED ===")
    try:
        data = request.get_json()
        print(f"Received data: {data}")
        
        effective_date = data.get('effective_date')
        state_code = data.get('state_code')
        zipcode = data.get('zipcode')
        
        print(f"Effective date: {effective_date}")
        print(f"State code: {state_code}")
        print(f"Zipcode: {zipcode}")
        
        radius_0_50 = float(data.get('radius_0_50', 0))
        radius_51_200 = float(data.get('radius_51_200', 0))
        radius_201_500 = float(data.get('radius_201_500', 0))
        radius_501_plus = float(data.get('radius_501_plus', 0))
        
        print(f"Radius values: {radius_0_50}, {radius_51_200}, {radius_201_500}, {radius_501_plus}")
        
        if not all([effective_date, state_code, zipcode]):
            print("ERROR: Missing required fields")
            return jsonify({
                'error': 'Missing required fields: effective_date, state_code, zipcode'
            }), 400
        
        default_factors = {
            '0-50': 1.29,
            '51-200': 1.49,
            '201-500': 1.69,
            '501+': 1.89
        }
        
        print("Connecting to database...")
        conn = get_db_connection()
        cur = conn.cursor()
        
        territory_query = """
            SELECT territory
            FROM ss_territory_lookup
            WHERE state_code = %s
              AND zipcode = %s
              AND effective_date <= %s
            ORDER BY effective_date DESC
            LIMIT 1
        """
        
        print(f"Looking up territory with: {state_code}, {zipcode}, {effective_date}")
        cur.execute(territory_query, (state_code, zipcode, effective_date))
        territory_result = cur.fetchone()
        print(f"Territory result: {territory_result}")
        
        if not territory_result:
            print("No territory found, using defaults")
            cur.close()
            conn.close()
            territory = 'DEFAULT'
            factor_0_50 = default_factors['0-50']
            factor_51_200 = default_factors['51-200']
            factor_201_500 = default_factors['201-500']
            factor_501_plus = default_factors['501+']
        else:
            territory = territory_result[0]
            print(f"Territory found: {territory}")
            
            count_query = "SELECT COUNT(*) FROM ss_umpd_radius_factor WHERE state_code = %s AND territory = %s"
            cur.execute(count_query, (state_code, territory))
            count_result = cur.fetchone()
            print(f"Number of UMPD radius factor records for {state_code}/{territory}: {count_result[0]}")
            
            date_query = """
                SELECT MAX(effective_date) as max_date
                FROM ss_umpd_radius_factor
                WHERE state_code = %s
                  AND territory = %s
                  AND effective_date <= %s
            """
            
            cur.execute(date_query, (state_code, territory, effective_date))
            date_result = cur.fetchone()
            print(f"Max effective date: {date_result}")
            
            if date_result and date_result[0]:
                max_effective_date = date_result[0]
                
                radius_query = """
                    SELECT radius_category, factor
                    FROM ss_umpd_radius_factor
                    WHERE state_code = %s
                      AND territory = %s
                      AND effective_date = %s
                """
                
                cur.execute(radius_query, (state_code, territory, max_effective_date))
                radius_results = cur.fetchall()
                print(f"Radius results: {radius_results}")
                
                factors = {}
                for row in radius_results:
                    factors[row[0]] = float(row[1])
                
                factor_0_50 = factors.get('0-50', default_factors['0-50'])
                factor_51_200 = factors.get('51-200', default_factors['51-200'])
                factor_201_500 = factors.get('201-500', default_factors['201-500'])
                factor_501_plus = factors.get('501+', default_factors['501+'])
            else:
                print("No UMPD radius factors found, using defaults")
                factor_0_50 = default_factors['0-50']
                factor_51_200 = default_factors['51-200']
                factor_201_500 = default_factors['201-500']
                factor_501_plus = default_factors['501+']
        
        cur.close()
        conn.close()
        
        print(f"Factors being used: {factor_0_50}, {factor_51_200}, {factor_201_500}, {factor_501_plus}")
        
        weighted_factor = (
            (radius_0_50 / 100.0 * factor_0_50) +
            (radius_51_200 / 100.0 * factor_51_200) +
            (radius_201_500 / 100.0 * factor_201_500) +
            (radius_501_plus / 100.0 * factor_501_plus)
        )
        
        weighted_factor = round(weighted_factor, 4)
        
        print(f"Weighted factor calculated: {weighted_factor}")
        
        return jsonify({
            'state_code': state_code,
            'territory': territory,
            'weighted_factor': weighted_factor,
            'factors_used': {
                '0-50': factor_0_50,
                '51-200': factor_51_200,
                '201-500': factor_201_500,
                '501+': factor_501_plus
            },
            'percentages': {
                '0-50': radius_0_50,
                '51-200': radius_51_200,
                '201-500': radius_201_500,
                '501+': radius_501_plus
            }
        })
            
    except Exception as e:
        print(f"!!! EXCEPTION OCCURRED !!!")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# --- SS (Non Admitted) UIMBI BASE RATE ENDPOINT ---
@app.route("/rate/ss_uimbi", methods=["POST"])
def rate_ss_uimbi():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS UIMBI - Date: {policy_date}, State: {state_code}")
        
        base_rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate FROM ss_uimbi_base_rates
            WHERE effective_date <= %s AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            base_rate = result[0]
            print(f"DEBUG SS UIMBI - Found rate: {base_rate}")
        else:
            print(f"DEBUG SS UIMBI - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"base_rate": str(base_rate)})
    except Exception as e:
        print(f"SS UIMBI Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) UIMBI ILF FACTOR ENDPOINT ---
@app.route("/rate/ss_uimbi_ilf_factor", methods=["POST"])
def rate_ss_uimbi_ilf_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS UIMBI ILF Factor - Date: {policy_date}, State: {state_code}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_uimbi_ilf_factor
            WHERE effective_date <= %s 
              AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS UIMBI ILF Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS UIMBI ILF Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS UIMBI ILF Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) UIMBI BODY TYPE BUSINESS FACTOR ENDPOINT ---
@app.route("/rate/ss_uimbi_btb_factor", methods=["POST"])
def rate_ss_uimbi_btb_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        vehicle_class = data.get("vehicle_class")
        business_use_type = data.get("business_use_type")
        
        print(f"DEBUG SS UIMBI BTB Factor - Date: {policy_date}, State: {state_code}, Body: {body_type}, Class: {vehicle_class}, Business: {business_use_type}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_uimbi_btb_factor
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND vehicle_class = %s
              AND business_use_type = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, vehicle_class, business_use_type))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS UIMBI BTB Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS UIMBI BTB Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS UIMBI BTB Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) UIMBI BODY TYPE BUSINESS CLASS TRAILER FACTOR ENDPOINT ---
@app.route("/rate/ss_uimbi_btbct_factor", methods=["POST"])
def rate_ss_uimbi_btbct_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        business_use_type = data.get("business_use_type")
        
        print(f"DEBUG SS UIMBI BTBCT Factor - Date: {policy_date}, State: {state_code}, Body: {body_type}, Business: {business_use_type}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_uimbi_btbct_factor
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND business_use_type = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, business_use_type))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS UIMBI BTBCT Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS UIMBI BTBCT Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS UIMBI BTBCT Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS UIMBI Radius Factor ---
@app.route('/rate/ss_uimbi_radius_factor', methods=['POST'])
def get_ss_uimbi_radius_factor():
    """
    Get Non Admitted UIMBI weighted radius factor
    """
    print("=== SS UIMBI RADIUS FACTOR CALLED ===")
    try:
        data = request.get_json()
        print(f"Received data: {data}")
        
        effective_date = data.get('effective_date')
        state_code = data.get('state_code')
        zipcode = data.get('zipcode')
        
        print(f"Effective date: {effective_date}")
        print(f"State code: {state_code}")
        print(f"Zipcode: {zipcode}")
        
        radius_0_50 = float(data.get('radius_0_50', 0))
        radius_51_200 = float(data.get('radius_51_200', 0))
        radius_201_500 = float(data.get('radius_201_500', 0))
        radius_501_plus = float(data.get('radius_501_plus', 0))
        
        print(f"Radius values: {radius_0_50}, {radius_51_200}, {radius_201_500}, {radius_501_plus}")
        
        if not all([effective_date, state_code, zipcode]):
            print("ERROR: Missing required fields")
            return jsonify({
                'error': 'Missing required fields: effective_date, state_code, zipcode'
            }), 400
        
        default_factors = {
            '0-50': 1.29,
            '51-200': 1.49,
            '201-500': 1.69,
            '501+': 1.89
        }
        
        print("Connecting to database...")
        conn = get_db_connection()
        cur = conn.cursor()
        
        territory_query = """
            SELECT territory
            FROM ss_territory_lookup
            WHERE state_code = %s
              AND zipcode = %s
              AND effective_date <= %s
            ORDER BY effective_date DESC
            LIMIT 1
        """
        
        print(f"Looking up territory with: {state_code}, {zipcode}, {effective_date}")
        cur.execute(territory_query, (state_code, zipcode, effective_date))
        territory_result = cur.fetchone()
        print(f"Territory result: {territory_result}")
        
        if not territory_result:
            print("No territory found, using defaults")
            cur.close()
            conn.close()
            territory = 'DEFAULT'
            factor_0_50 = default_factors['0-50']
            factor_51_200 = default_factors['51-200']
            factor_201_500 = default_factors['201-500']
            factor_501_plus = default_factors['501+']
        else:
            territory = territory_result[0]
            print(f"Territory found: {territory}")
            
            count_query = "SELECT COUNT(*) FROM ss_uimbi_radius_factor WHERE state_code = %s AND territory = %s"
            cur.execute(count_query, (state_code, territory))
            count_result = cur.fetchone()
            print(f"Number of UIMBI radius factor records for {state_code}/{territory}: {count_result[0]}")
            
            date_query = """
                SELECT MAX(effective_date) as max_date
                FROM ss_uimbi_radius_factor
                WHERE state_code = %s
                  AND territory = %s
                  AND effective_date <= %s
            """
            
            cur.execute(date_query, (state_code, territory, effective_date))
            date_result = cur.fetchone()
            print(f"Max effective date: {date_result}")
            
            if date_result and date_result[0]:
                max_effective_date = date_result[0]
                
                radius_query = """
                    SELECT radius_category, factor
                    FROM ss_uimbi_radius_factor
                    WHERE state_code = %s
                      AND territory = %s
                      AND effective_date = %s
                """
                
                cur.execute(radius_query, (state_code, territory, max_effective_date))
                radius_results = cur.fetchall()
                print(f"Radius results: {radius_results}")
                
                factors = {}
                for row in radius_results:
                    factors[row[0]] = float(row[1])
                
                factor_0_50 = factors.get('0-50', default_factors['0-50'])
                factor_51_200 = factors.get('51-200', default_factors['51-200'])
                factor_201_500 = factors.get('201-500', default_factors['201-500'])
                factor_501_plus = factors.get('501+', default_factors['501+'])
            else:
                print("No UIMBI radius factors found, using defaults")
                factor_0_50 = default_factors['0-50']
                factor_51_200 = default_factors['51-200']
                factor_201_500 = default_factors['201-500']
                factor_501_plus = default_factors['501+']
        
        cur.close()
        conn.close()
        
        print(f"Factors being used: {factor_0_50}, {factor_51_200}, {factor_201_500}, {factor_501_plus}")
        
        weighted_factor = (
            (radius_0_50 / 100.0 * factor_0_50) +
            (radius_51_200 / 100.0 * factor_51_200) +
            (radius_201_500 / 100.0 * factor_201_500) +
            (radius_501_plus / 100.0 * factor_501_plus)
        )
        
        weighted_factor = round(weighted_factor, 4)
        
        print(f"Weighted factor calculated: {weighted_factor}")
        
        return jsonify({
            'state_code': state_code,
            'territory': territory,
            'weighted_factor': weighted_factor,
            'factors_used': {
                '0-50': factor_0_50,
                '51-200': factor_51_200,
                '201-500': factor_201_500,
                '501+': factor_501_plus
            },
            'percentages': {
                '0-50': radius_0_50,
                '51-200': radius_51_200,
                '201-500': radius_201_500,
                '501+': radius_501_plus
            }
        })
            
    except Exception as e:
        print(f"!!! EXCEPTION OCCURRED !!!")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
# --- SS (Non Admitted) UIMPD BASE RATE ENDPOINT ---
@app.route("/rate/ss_uimpd", methods=["POST"])
def rate_ss_uimpd():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS UIMPD - Date: {policy_date}, State: {state_code}")
        
        base_rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate FROM ss_uimpd_base_rates
            WHERE effective_date <= %s AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            base_rate = result[0]
            print(f"DEBUG SS UIMPD - Found rate: {base_rate}")
        else:
            print(f"DEBUG SS UIMPD - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"base_rate": str(base_rate)})
    except Exception as e:
        print(f"SS UIMPD Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) UIMPD ILF FACTOR ENDPOINT ---
@app.route("/rate/ss_uimpd_ilf_factor", methods=["POST"])
def rate_ss_uimpd_ilf_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS UIMPD ILF Factor - Date: {policy_date}, State: {state_code}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_uimpd_ilf_factor
            WHERE effective_date <= %s 
              AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS UIMPD ILF Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS UIMPD ILF Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS UIMPD ILF Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) UIMPD BODY TYPE BUSINESS FACTOR ENDPOINT ---
@app.route("/rate/ss_uimpd_btb_factor", methods=["POST"])
def rate_ss_uimpd_btb_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        vehicle_class = data.get("vehicle_class")
        business_use_type = data.get("business_use_type")
        
        print(f"DEBUG SS UIMPD BTB Factor - Date: {policy_date}, State: {state_code}, Body: {body_type}, Class: {vehicle_class}, Business: {business_use_type}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_uimpd_btb_factor
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND vehicle_class = %s
              AND business_use_type = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, vehicle_class, business_use_type))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS UIMPD BTB Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS UIMPD BTB Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS UIMPD BTB Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) UIMPD BODY TYPE BUSINESS CLASS TRAILER FACTOR ENDPOINT ---
@app.route("/rate/ss_uimpd_btbct_factor", methods=["POST"])
def rate_ss_uimpd_btbct_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        business_use_type = data.get("business_use_type")
        
        print(f"DEBUG SS UIMPD BTBCT Factor - Date: {policy_date}, State: {state_code}, Body: {body_type}, Business: {business_use_type}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_uimpd_btbct_factor
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND business_use_type = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, business_use_type))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS UIMPD BTBCT Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS UIMPD BTBCT Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS UIMPD BTBCT Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS UIMPD Radius Factor ---
@app.route('/rate/ss_uimpd_radius_factor', methods=['POST'])
def get_ss_uimpd_radius_factor():
    """
    Get Non Admitted UIMPD weighted radius factor
    """
    print("=== SS UIMPD RADIUS FACTOR CALLED ===")
    try:
        data = request.get_json()
        print(f"Received data: {data}")
        
        effective_date = data.get('effective_date')
        state_code = data.get('state_code')
        zipcode = data.get('zipcode')
        
        print(f"Effective date: {effective_date}")
        print(f"State code: {state_code}")
        print(f"Zipcode: {zipcode}")
        
        radius_0_50 = float(data.get('radius_0_50', 0))
        radius_51_200 = float(data.get('radius_51_200', 0))
        radius_201_500 = float(data.get('radius_201_500', 0))
        radius_501_plus = float(data.get('radius_501_plus', 0))
        
        print(f"Radius values: {radius_0_50}, {radius_51_200}, {radius_201_500}, {radius_501_plus}")
        
        if not all([effective_date, state_code, zipcode]):
            print("ERROR: Missing required fields")
            return jsonify({
                'error': 'Missing required fields: effective_date, state_code, zipcode'
            }), 400
        
        default_factors = {
            '0-50': 1.29,
            '51-200': 1.49,
            '201-500': 1.69,
            '501+': 1.89
        }
        
        print("Connecting to database...")
        conn = get_db_connection()
        cur = conn.cursor()
        
        territory_query = """
            SELECT territory
            FROM ss_territory_lookup
            WHERE state_code = %s
              AND zipcode = %s
              AND effective_date <= %s
            ORDER BY effective_date DESC
            LIMIT 1
        """
        
        print(f"Looking up territory with: {state_code}, {zipcode}, {effective_date}")
        cur.execute(territory_query, (state_code, zipcode, effective_date))
        territory_result = cur.fetchone()
        print(f"Territory result: {territory_result}")
        
        if not territory_result:
            print("No territory found, using defaults")
            cur.close()
            conn.close()
            territory = 'DEFAULT'
            factor_0_50 = default_factors['0-50']
            factor_51_200 = default_factors['51-200']
            factor_201_500 = default_factors['201-500']
            factor_501_plus = default_factors['501+']
        else:
            territory = territory_result[0]
            print(f"Territory found: {territory}")
            
            count_query = "SELECT COUNT(*) FROM ss_uimpd_radius_factor WHERE state_code = %s AND territory = %s"
            cur.execute(count_query, (state_code, territory))
            count_result = cur.fetchone()
            print(f"Number of UIMPD radius factor records for {state_code}/{territory}: {count_result[0]}")
            
            date_query = """
                SELECT MAX(effective_date) as max_date
                FROM ss_uimpd_radius_factor
                WHERE state_code = %s
                  AND territory = %s
                  AND effective_date <= %s
            """
            
            cur.execute(date_query, (state_code, territory, effective_date))
            date_result = cur.fetchone()
            print(f"Max effective date: {date_result}")
            
            if date_result and date_result[0]:
                max_effective_date = date_result[0]
                
                radius_query = """
                    SELECT radius_category, factor
                    FROM ss_uimpd_radius_factor
                    WHERE state_code = %s
                      AND territory = %s
                      AND effective_date = %s
                """
                
                cur.execute(radius_query, (state_code, territory, max_effective_date))
                radius_results = cur.fetchall()
                print(f"Radius results: {radius_results}")
                
                factors = {}
                for row in radius_results:
                    factors[row[0]] = float(row[1])
                
                factor_0_50 = factors.get('0-50', default_factors['0-50'])
                factor_51_200 = factors.get('51-200', default_factors['51-200'])
                factor_201_500 = factors.get('201-500', default_factors['201-500'])
                factor_501_plus = factors.get('501+', default_factors['501+'])
            else:
                print("No UIMPD radius factors found, using defaults")
                factor_0_50 = default_factors['0-50']
                factor_51_200 = default_factors['51-200']
                factor_201_500 = default_factors['201-500']
                factor_501_plus = default_factors['501+']
        
        cur.close()
        conn.close()
        
        print(f"Factors being used: {factor_0_50}, {factor_51_200}, {factor_201_500}, {factor_501_plus}")
        
        weighted_factor = (
            (radius_0_50 / 100.0 * factor_0_50) +
            (radius_51_200 / 100.0 * factor_51_200) +
            (radius_201_500 / 100.0 * factor_201_500) +
            (radius_501_plus / 100.0 * factor_501_plus)
        )
        
        weighted_factor = round(weighted_factor, 4)
        
        print(f"Weighted factor calculated: {weighted_factor}")
        
        return jsonify({
            'state_code': state_code,
            'territory': territory,
            'weighted_factor': weighted_factor,
            'factors_used': {
                '0-50': factor_0_50,
                '51-200': factor_51_200,
                '201-500': factor_201_500,
                '501+': factor_501_plus
            },
            'percentages': {
                '0-50': radius_0_50,
                '51-200': radius_51_200,
                '201-500': radius_201_500,
                '501+': radius_501_plus
            }
        })
            
    except Exception as e:
        print(f"!!! EXCEPTION OCCURRED !!!")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
# --- SS (Non Admitted) MEDICAL PAYMENTS BASE RATE ENDPOINT ---
@app.route("/rate/ss_medpay", methods=["POST"])
def rate_ss_medpay():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS MedPay - Date: {policy_date}, State: {state_code}")
        
        base_rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate FROM ss_medpay_base_rates
            WHERE effective_date <= %s AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            base_rate = result[0]
            print(f"DEBUG SS MedPay - Found rate: {base_rate}")
        else:
            print(f"DEBUG SS MedPay - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"base_rate": str(base_rate)})
    except Exception as e:
        print(f"SS MedPay Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) MEDICAL PAYMENTS BTBC FACTOR ENDPOINT ---
@app.route("/rate/ss_medpay_btbc_factor", methods=["POST"])
def rate_ss_medpay_btbc_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        vehicle_class = data.get("vehicle_class")
        business_use_type = data.get("business_use_type")
        
        print(f"DEBUG SS MedPay BTBC - Date: {policy_date}, State: {state_code}, Body: {body_type}, Class: {vehicle_class}, Business: {business_use_type}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_medpay_btbc
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND vehicle_class = %s
              AND business_use_type = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, vehicle_class, business_use_type))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS MedPay BTBC - Found factor: {factor}")
        else:
            print(f"DEBUG SS MedPay BTBC - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS MedPay BTBC Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) MEDICAL PAYMENTS BTBCTF FACTOR ENDPOINT ---
@app.route("/rate/ss_medpay_btbctf_factor", methods=["POST"])
def rate_ss_medpay_btbctf_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        business_use_type = data.get("business_use_type")
        
        print(f"DEBUG SS MedPay BTBCTF - Date: {policy_date}, State: {state_code}, Body: {body_type}, Business: {business_use_type}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_medpay_btbctf
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND business_use_type = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, business_use_type))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS MedPay BTBCTF - Found factor: {factor}")
        else:
            print(f"DEBUG SS MedPay BTBCTF - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS MedPay BTBCTF Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) MEDICAL PAYMENTS MODEL YEAR FACTOR ENDPOINT ---
@app.route("/rate/ss_medpay_model_year_factor", methods=["POST"])
def rate_ss_medpay_model_year_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        vehicle_class = data.get("vehicle_class")
        vehicle_year = int(data.get("vehicle_year", 0))
        non_owned_trailer = data.get("non_owned_trailer", False)
        
        print(f"DEBUG SS MedPay Model Year - Date: {policy_date}, State: {state_code}, Body: {body_type}, Class: {vehicle_class}, Year: {vehicle_year}, NonOwned: {non_owned_trailer}")
        
        if non_owned_trailer:
            print(f"DEBUG SS MedPay Model Year - Non Owned Trailer, returning 1.0")
            return jsonify({"factor": "1.0"})
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_medpay_model_year
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND vehicle_class = %s
              AND minimum_year <= %s
              AND maximum_year >= %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, vehicle_class, vehicle_year, vehicle_year))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS MedPay Model Year - Found factor: {factor}")
        else:
            print(f"DEBUG SS MedPay Model Year - No factor found for year {vehicle_year}, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS MedPay Model Year Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) MEDICAL PAYMENTS MODEL YEAR TRAILER FACTOR ENDPOINT ---
@app.route("/rate/ss_medpay_model_year_trailer_factor", methods=["POST"])
def rate_ss_medpay_model_year_trailer_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        vehicle_year = int(data.get("vehicle_year", 0))
        non_owned_trailer = data.get("non_owned_trailer", False)
        
        print(f"DEBUG SS MedPay Model Year Trailer - Date: {policy_date}, State: {state_code}, Body: {body_type}, Year: {vehicle_year}, NonOwned: {non_owned_trailer}")
        
        if non_owned_trailer:
            print(f"DEBUG SS MedPay Model Year Trailer - Non Owned Trailer, returning 1.0")
            return jsonify({"factor": "1.0"})
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_medpay_model_year_trailer
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND minimum_year <= %s
              AND maximum_year >= %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, vehicle_year, vehicle_year))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS MedPay Model Year Trailer - Found factor: {factor}")
        else:
            print(f"DEBUG SS MedPay Model Year Trailer - No factor found for year {vehicle_year}, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS MedPay Model Year Trailer Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) MEDICAL PAYMENTS ILF FACTOR ENDPOINT ---
@app.route("/rate/ss_medpay_ilf_factor", methods=["POST"])
def rate_ss_medpay_ilf_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS MedPay ILF Factor - Date: {policy_date}, State: {state_code}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_medpay_ilf
            WHERE effective_date <= %s 
              AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS MedPay ILF Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS MedPay ILF Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS MedPay ILF Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS MEDICAL PAYMENTS Radius Factor ---
@app.route('/rate/ss_medpay_radius_factor', methods=['POST'])
def get_ss_medpay_radius_factor():
    """
    Get Non Admitted Medical Payments weighted radius factor
    """
    print("=== SS MEDPAY RADIUS FACTOR CALLED ===")
    try:
        data = request.get_json()
        print(f"Received data: {data}")
        
        effective_date = data.get('effective_date')
        state_code = data.get('state_code')
        zipcode = data.get('zipcode')
        
        print(f"Effective date: {effective_date}")
        print(f"State code: {state_code}")
        print(f"Zipcode: {zipcode}")
        
        radius_0_50 = float(data.get('radius_0_50', 0))
        radius_51_200 = float(data.get('radius_51_200', 0))
        radius_201_500 = float(data.get('radius_201_500', 0))
        radius_501_plus = float(data.get('radius_501_plus', 0))
        
        print(f"Radius values: {radius_0_50}, {radius_51_200}, {radius_201_500}, {radius_501_plus}")
        
        if not all([effective_date, state_code, zipcode]):
            print("ERROR: Missing required fields")
            return jsonify({
                'error': 'Missing required fields: effective_date, state_code, zipcode'
            }), 400
        
        default_factors = {
            '0-50': 1.29,
            '51-200': 1.49,
            '201-500': 1.69,
            '501+': 1.89
        }
        
        print("Connecting to database...")
        conn = get_db_connection()
        cur = conn.cursor()
        
        territory_query = """
            SELECT territory
            FROM ss_territory_lookup
            WHERE state_code = %s
              AND zipcode = %s
              AND effective_date <= %s
            ORDER BY effective_date DESC
            LIMIT 1
        """
        
        print(f"Looking up territory with: {state_code}, {zipcode}, {effective_date}")
        cur.execute(territory_query, (state_code, zipcode, effective_date))
        territory_result = cur.fetchone()
        print(f"Territory result: {territory_result}")
        
        if not territory_result:
            print("No territory found, using defaults")
            cur.close()
            conn.close()
            territory = 'DEFAULT'
            factor_0_50 = default_factors['0-50']
            factor_51_200 = default_factors['51-200']
            factor_201_500 = default_factors['201-500']
            factor_501_plus = default_factors['501+']
        else:
            territory = territory_result[0]
            print(f"Territory found: {territory}")
            
            count_query = "SELECT COUNT(*) FROM ss_medpay_radius_factor WHERE state_code = %s AND territory = %s"
            cur.execute(count_query, (state_code, territory))
            count_result = cur.fetchone()
            print(f"Number of MedPay radius factor records for {state_code}/{territory}: {count_result[0]}")
            
            date_query = """
                SELECT MAX(effective_date) as max_date
                FROM ss_medpay_radius_factor
                WHERE state_code = %s
                  AND territory = %s
                  AND effective_date <= %s
            """
            
            cur.execute(date_query, (state_code, territory, effective_date))
            date_result = cur.fetchone()
            print(f"Max effective date: {date_result}")
            
            if date_result and date_result[0]:
                max_effective_date = date_result[0]
                
                radius_query = """
                    SELECT radius_category, factor
                    FROM ss_medpay_radius_factor
                    WHERE state_code = %s
                      AND territory = %s
                      AND effective_date = %s
                """
                
                cur.execute(radius_query, (state_code, territory, max_effective_date))
                radius_results = cur.fetchall()
                print(f"Radius results: {radius_results}")
                
                factors = {}
                for row in radius_results:
                    factors[row[0]] = float(row[1])
                
                factor_0_50 = factors.get('0-50', default_factors['0-50'])
                factor_51_200 = factors.get('51-200', default_factors['51-200'])
                factor_201_500 = factors.get('201-500', default_factors['201-500'])
                factor_501_plus = factors.get('501+', default_factors['501+'])
            else:
                print("No MedPay radius factors found, using defaults")
                factor_0_50 = default_factors['0-50']
                factor_51_200 = default_factors['51-200']
                factor_201_500 = default_factors['201-500']
                factor_501_plus = default_factors['501+']
        
        cur.close()
        conn.close()
        
        print(f"Factors being used: {factor_0_50}, {factor_51_200}, {factor_201_500}, {factor_501_plus}")
        
        weighted_factor = (
            (radius_0_50 / 100.0 * factor_0_50) +
            (radius_51_200 / 100.0 * factor_51_200) +
            (radius_201_500 / 100.0 * factor_201_500) +
            (radius_501_plus / 100.0 * factor_501_plus)
        )
        
        weighted_factor = round(weighted_factor, 4)
        
        print(f"Weighted factor calculated: {weighted_factor}")
        
        return jsonify({
            'state_code': state_code,
            'territory': territory,
            'weighted_factor': weighted_factor,
            'factors_used': {
                '0-50': factor_0_50,
                '51-200': factor_51_200,
                '201-500': factor_201_500,
                '501+': factor_501_plus
            },
            'percentages': {
                '0-50': radius_0_50,
                '51-200': radius_51_200,
                '201-500': radius_201_500,
                '501+': radius_501_plus
            }
        })
            
    except Exception as e:
        print(f"!!! EXCEPTION OCCURRED !!!")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
# --- SS (Non Admitted) PIP BASE RATE ENDPOINT ---
@app.route("/rate/ss_pip", methods=["POST"])
def rate_ss_pip():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS PIP - Date: {policy_date}, State: {state_code}")
        
        base_rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate FROM ss_pip_base_rates
            WHERE effective_date <= %s AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            base_rate = result[0]
            print(f"DEBUG SS PIP - Found rate: {base_rate}")
        else:
            print(f"DEBUG SS PIP - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"base_rate": str(base_rate)})
    except Exception as e:
        print(f"SS PIP Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) PIP BTBC FACTOR ENDPOINT ---
@app.route("/rate/ss_pip_btbc_factor", methods=["POST"])
def rate_ss_pip_btbc_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        vehicle_class = data.get("vehicle_class")
        business_use_type = data.get("business_use_type")
        
        print(f"DEBUG SS PIP BTBC - Date: {policy_date}, State: {state_code}, Body: {body_type}, Class: {vehicle_class}, Business: {business_use_type}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_pip_btbc
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND vehicle_class = %s
              AND business_use_type = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, vehicle_class, business_use_type))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS PIP BTBC - Found factor: {factor}")
        else:
            print(f"DEBUG SS PIP BTBC - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS PIP BTBC Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) PIP BTBCTF FACTOR ENDPOINT ---
@app.route("/rate/ss_pip_btbctf_factor", methods=["POST"])
def rate_ss_pip_btbctf_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        business_use_type = data.get("business_use_type")
        
        print(f"DEBUG SS PIP BTBCTF - Date: {policy_date}, State: {state_code}, Body: {body_type}, Business: {business_use_type}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_pip_btbctf
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND business_use_type = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, business_use_type))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS PIP BTBCTF - Found factor: {factor}")
        else:
            print(f"DEBUG SS PIP BTBCTF - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS PIP BTBCTF Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) PIP MODEL YEAR FACTOR ENDPOINT ---
@app.route("/rate/ss_pip_model_year_factor", methods=["POST"])
def rate_ss_pip_model_year_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        vehicle_class = data.get("vehicle_class")
        vehicle_year = int(data.get("vehicle_year", 0))
        non_owned_trailer = data.get("non_owned_trailer", False)
        
        print(f"DEBUG SS PIP Model Year - Date: {policy_date}, State: {state_code}, Body: {body_type}, Class: {vehicle_class}, Year: {vehicle_year}, NonOwned: {non_owned_trailer}")
        
        if non_owned_trailer:
            print(f"DEBUG SS PIP Model Year - Non Owned Trailer, returning 1.0")
            return jsonify({"factor": "1.0"})
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_pip_model_year
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND vehicle_class = %s
              AND minimum_year <= %s
              AND maximum_year >= %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, vehicle_class, vehicle_year, vehicle_year))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS PIP Model Year - Found factor: {factor}")
        else:
            print(f"DEBUG SS PIP Model Year - No factor found for year {vehicle_year}, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS PIP Model Year Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) PIP MODEL YEAR TRAILER FACTOR ENDPOINT ---
@app.route("/rate/ss_pip_model_year_trailer_factor", methods=["POST"])
def rate_ss_pip_model_year_trailer_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        vehicle_year = int(data.get("vehicle_year", 0))
        non_owned_trailer = data.get("non_owned_trailer", False)
        
        print(f"DEBUG SS PIP Model Year Trailer - Date: {policy_date}, State: {state_code}, Body: {body_type}, Year: {vehicle_year}, NonOwned: {non_owned_trailer}")
        
        if non_owned_trailer:
            print(f"DEBUG SS PIP Model Year Trailer - Non Owned Trailer, returning 1.0")
            return jsonify({"factor": "1.0"})
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_pip_model_year_trailer
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND minimum_year <= %s
              AND maximum_year >= %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, vehicle_year, vehicle_year))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS PIP Model Year Trailer - Found factor: {factor}")
        else:
            print(f"DEBUG SS PIP Model Year Trailer - No factor found for year {vehicle_year}, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS PIP Model Year Trailer Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) PIP ILF FACTOR ENDPOINT ---
@app.route("/rate/ss_pip_ilf_factor", methods=["POST"])
def rate_ss_pip_ilf_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS PIP ILF Factor - Date: {policy_date}, State: {state_code}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_pip_ilf
            WHERE effective_date <= %s 
              AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS PIP ILF Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS PIP ILF Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS PIP ILF Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS PIP Radius Factor ---
@app.route('/rate/ss_pip_radius_factor', methods=['POST'])
def get_ss_pip_radius_factor():
    """
    Get Non Admitted PIP weighted radius factor
    """
    print("=== SS PIP RADIUS FACTOR CALLED ===")
    try:
        data = request.get_json()
        print(f"Received data: {data}")
        
        effective_date = data.get('effective_date')
        state_code = data.get('state_code')
        zipcode = data.get('zipcode')
        
        print(f"Effective date: {effective_date}")
        print(f"State code: {state_code}")
        print(f"Zipcode: {zipcode}")
        
        radius_0_50 = float(data.get('radius_0_50', 0))
        radius_51_200 = float(data.get('radius_51_200', 0))
        radius_201_500 = float(data.get('radius_201_500', 0))
        radius_501_plus = float(data.get('radius_501_plus', 0))
        
        print(f"Radius values: {radius_0_50}, {radius_51_200}, {radius_201_500}, {radius_501_plus}")
        
        if not all([effective_date, state_code, zipcode]):
            print("ERROR: Missing required fields")
            return jsonify({
                'error': 'Missing required fields: effective_date, state_code, zipcode'
            }), 400
        
        default_factors = {
            '0-50': 1.29,
            '51-200': 1.49,
            '201-500': 1.69,
            '501+': 1.89
        }
        
        print("Connecting to database...")
        conn = get_db_connection()
        cur = conn.cursor()
        
        territory_query = """
            SELECT territory
            FROM ss_territory_lookup
            WHERE state_code = %s
              AND zipcode = %s
              AND effective_date <= %s
            ORDER BY effective_date DESC
            LIMIT 1
        """
        
        print(f"Looking up territory with: {state_code}, {zipcode}, {effective_date}")
        cur.execute(territory_query, (state_code, zipcode, effective_date))
        territory_result = cur.fetchone()
        print(f"Territory result: {territory_result}")
        
        if not territory_result:
            print("No territory found, using defaults")
            cur.close()
            conn.close()
            territory = 'DEFAULT'
            factor_0_50 = default_factors['0-50']
            factor_51_200 = default_factors['51-200']
            factor_201_500 = default_factors['201-500']
            factor_501_plus = default_factors['501+']
        else:
            territory = territory_result[0]
            print(f"Territory found: {territory}")
            
            count_query = "SELECT COUNT(*) FROM ss_pip_radius_factor WHERE state_code = %s AND territory = %s"
            cur.execute(count_query, (state_code, territory))
            count_result = cur.fetchone()
            print(f"Number of PIP radius factor records for {state_code}/{territory}: {count_result[0]}")
            
            date_query = """
                SELECT MAX(effective_date) as max_date
                FROM ss_pip_radius_factor
                WHERE state_code = %s
                  AND territory = %s
                  AND effective_date <= %s
            """
            
            cur.execute(date_query, (state_code, territory, effective_date))
            date_result = cur.fetchone()
            print(f"Max effective date: {date_result}")
            
            if date_result and date_result[0]:
                max_effective_date = date_result[0]
                
                radius_query = """
                    SELECT radius_category, factor
                    FROM ss_pip_radius_factor
                    WHERE state_code = %s
                      AND territory = %s
                      AND effective_date = %s
                """
                
                cur.execute(radius_query, (state_code, territory, max_effective_date))
                radius_results = cur.fetchall()
                print(f"Radius results: {radius_results}")
                
                factors = {}
                for row in radius_results:
                    factors[row[0]] = float(row[1])
                
                factor_0_50 = factors.get('0-50', default_factors['0-50'])
                factor_51_200 = factors.get('51-200', default_factors['51-200'])
                factor_201_500 = factors.get('201-500', default_factors['201-500'])
                factor_501_plus = factors.get('501+', default_factors['501+'])
            else:
                print("No PIP radius factors found, using defaults")
                factor_0_50 = default_factors['0-50']
                factor_51_200 = default_factors['51-200']
                factor_201_500 = default_factors['201-500']
                factor_501_plus = default_factors['501+']
        
        cur.close()
        conn.close()
        
        print(f"Factors being used: {factor_0_50}, {factor_51_200}, {factor_201_500}, {factor_501_plus}")
        
        weighted_factor = (
            (radius_0_50 / 100.0 * factor_0_50) +
            (radius_51_200 / 100.0 * factor_51_200) +
            (radius_201_500 / 100.0 * factor_201_500) +
            (radius_501_plus / 100.0 * factor_501_plus)
        )
        
        weighted_factor = round(weighted_factor, 4)
        
        print(f"Weighted factor calculated: {weighted_factor}")
        
        return jsonify({
            'state_code': state_code,
            'territory': territory,
            'weighted_factor': weighted_factor,
            'factors_used': {
                '0-50': factor_0_50,
                '51-200': factor_51_200,
                '201-500': factor_201_500,
                '501+': factor_501_plus
            },
            'percentages': {
                '0-50': radius_0_50,
                '51-200': radius_51_200,
                '201-500': radius_201_500,
                '501+': radius_501_plus
            }
        })
            
    except Exception as e:
        print(f"!!! EXCEPTION OCCURRED !!!")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
# --- SS (Non Admitted) HNOA BASE RATE ENDPOINT ---
@app.route("/rate/ss_hnoa", methods=["POST"])
def rate_ss_hnoa():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS HNOA - Date: {policy_date}, State: {state_code}")
        
        base_rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate FROM ss_hnoa_base_rates
            WHERE effective_date <= %s AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            base_rate = result[0]
            print(f"DEBUG SS HNOA - Found rate: {base_rate}")
        else:
            print(f"DEBUG SS HNOA - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"base_rate": str(base_rate)})
    except Exception as e:
        print(f"SS HNOA Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- UPDATED: RATING PLAN LOOKUP ENDPOINT (Uses PostgreSQL) ---
@app.route("/lookup/rating_plan", methods=["POST"])
def lookup_rating_plan():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        carrier_name = data.get("carrier_name")
        
        print(f"DEBUG Rating Plan Lookup - Date: {policy_date}, State: {state_code}, Carrier: {carrier_name}")
        
        plan_name = ""  # Default to empty
        
        # Connect to PostgreSQL database for rating plans
        conn = get_db_connection()
        cur = conn.cursor()
        
        # SQL query using %s placeholders for PostgreSQL
        sql = """
            SELECT rating_plan_name
            FROM auto_liability_rating_plans
            WHERE effective_date <= %s
              AND state_code = %s
              AND carrier_name = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, carrier_name))
        result = cur.fetchone()
        
        print(f"DEBUG Rating Plan Result: {result}")
        
        if result:
            plan_name = result[0]
            
        cur.close()
        conn.close()
        
        return jsonify({"plan_name": plan_name})
    
    except Exception as e:
        print(f"Rating Plan Lookup Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- NTL RATING ENDPOINT ---
@app.route("/rate/ntl", methods=["POST"])
def rate_ntl():
    try:
        data = request.json
        vehicle_count = int(data.get("num_vehicles"))
        policy_date = data.get("effective_date")
        premium = Decimal('0.0')
        conn = get_db_connection()
        cur = conn.cursor()
        sql = """
            SELECT rate_factor * %s AS ntl_premium
            FROM ntl_countrywide_baserate
            WHERE effective_date <= %s ORDER BY effective_date DESC LIMIT 1;
        """
        cur.execute(sql, (vehicle_count, policy_date))
        result = cur.fetchone()
        if result:
            premium = result[0]
        cur.close()
        conn.close()
        return jsonify({"premium": str(premium)})
    except Exception as e:
        print(f"NTL Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- TGL RATING ENDPOINT ---
@app.route("/rate/tgl", methods=["POST"])
def rate_tgl():
    try:
        data = request.json
        vehicle_count = int(data.get("num_vehicles"))
        policy_date = data.get("effective_date")
        premium = Decimal('0.0')
        conn = get_db_connection()
        cur = conn.cursor()
        sql = """
            SELECT premium FROM tgl_rates
            WHERE effective_date <= %s AND number_of_vehicles = %s
            ORDER BY effective_date DESC LIMIT 1;
        """
        cur.execute(sql, (policy_date, vehicle_count))
        result = cur.fetchone()
        if result:
            premium = result[0]
        cur.close()
        conn.close()
        return jsonify({"premium": str(premium)})
    except Exception as e:
        print(f"TGL Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- MTC RATING ENDPOINT ---
@app.route("/rate/mtc", methods=["POST"])
def rate_mtc():
    try:
        data = request.json
        vehicle_count = int(data.get("num_vehicles"))
        policy_date = data.get("effective_date")
        mtc_limit = data.get("mtc_limit")
        mtc_reefer = data.get("mtc_reefer")
        premium = Decimal('0.0')
        conn = get_db_connection()
        cur = conn.cursor()
        sql = """
            SELECT rate * %s AS mtc_premium FROM mtc_baserates
            WHERE effective_date <= %s AND limit_amount = %s AND has_refrigeration = %s
            ORDER BY effective_date DESC LIMIT 1;
        """
        cur.execute(sql, (vehicle_count, policy_date, mtc_limit, mtc_reefer))
        result = cur.fetchone()
        if result:
            premium = result[0]
        cur.close()
        conn.close()
        return jsonify({"premium": str(premium)})
    except Exception as e:
        print(f"MTC Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- TRAILER INTERCHANGE RATING ENDPOINT ---
@app.route("/rate/ti", methods=["POST"])
def rate_ti():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        ti_limit = Decimal(str(data.get("ti_limit") or 0))
        ti_uiia = data.get("ti_uiia")
        num_vehicles = Decimal(str(data.get("num_vehicles") or 0))
        num_trailers = Decimal(str(data.get("num_trailers") or 0))

        conn = get_db_connection()
        cur = conn.cursor()
        sql = """
            SELECT rate FROM mtc_trailerinterchange_rates
            WHERE effective_date <= %s AND has_uiia_exposure = %s
            ORDER BY effective_date DESC LIMIT 1;
        """
        cur.execute(sql, (policy_date, ti_uiia))
        result = cur.fetchone()
        cur.close()
        conn.close()

        if result:
            ti_rate = Decimal(result[0])
            exposure_units = max(num_vehicles - num_trailers, 1)
            premium = ti_rate * ti_limit * exposure_units
        else:
            premium = Decimal('0.0')

        return jsonify({"premium": str(round(premium, 2))})

    except Exception as e:
        print(f"TI Error: {e}")
        return jsonify({"error": str(e)}), 500
    
# --- TRIA RATE LOOKUP ENDPOINT ---
@app.route("/get/tria_rate", methods=["POST"])
def get_tria_rate():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        coverage_type = data.get("coverage_type")
        accepted = data.get("accepted")
        rate = Decimal('0.0')
        conn = get_db_connection()
        cur = conn.cursor()
        sql = """
            SELECT rate FROM tria_rates
            WHERE effective_date <= %s AND coverage_type = %s AND accepted = %s
            ORDER BY effective_date DESC LIMIT 1;
        """
        cur.execute(sql, (policy_date, coverage_type, accepted))
        result = cur.fetchone()
        if result:
            rate = result[0]
        cur.close()
        conn.close()
        return jsonify({"rate": str(rate)})
    except Exception as e:
        print(f"TRIA Rate Error: {e}")
        return jsonify({"error": str(e)}), 500
    
# --- SS (Non Admitted) BIPD BASE RATE ENDPOINT ---
@app.route("/rate/ss_bipd", methods=["POST"])
def rate_ss_bipd():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS BIPD - Date: {policy_date}, State: {state_code}")
        
        base_rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate FROM ss_bi_base_rates
            WHERE effective_date <= %s AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            base_rate = result[0]
            print(f"DEBUG SS BIPD - Found rate: {base_rate}")
        else:
            print(f"DEBUG SS BIPD - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"base_rate": str(base_rate)})
    except Exception as e:
        print(f"SS BIPD Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- SS (Non Admitted) PD BASE RATE ENDPOINT ---
@app.route("/rate/ss_pd", methods=["POST"])
def rate_ss_pd():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG SS PD - Date: {policy_date}, State: {state_code}")
        
        base_rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate FROM ss_pd_base_rates
            WHERE effective_date <= %s AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            base_rate = result[0]
            print(f"DEBUG SS PD - Found rate: {base_rate}")
        else:
            print(f"DEBUG SS PD - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"base_rate": str(base_rate)})
    except Exception as e:
        print(f"SS PD Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- SS (Non Admitted) BODY TYPE BUSINESS CLASS FACTOR ENDPOINT ---
@app.route("/rate/ss_btbc_factor", methods=["POST"])
def rate_ss_btbc_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        vehicle_class = data.get("vehicle_class")
        business_use_type = data.get("business_use_type")
        
        print(f"DEBUG SS BTBC - Date: {policy_date}, State: {state_code}, Body: {body_type}, Class: {vehicle_class}, Business: {business_use_type}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_btbc
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND vehicle_class = %s
              AND business_use_type = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, vehicle_class, business_use_type))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS BTBC - Found factor: {factor}")
        else:
            print(f"DEBUG SS BTBC - No factor found for criteria, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS BTBC Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- SS (Non Admitted) BODY TYPE BUSINESS CLASS TRAILER FACTOR ENDPOINT ---
@app.route("/rate/ss_btbctf_factor", methods=["POST"])
def rate_ss_btbctf_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        business_use_type = data.get("business_use_type")
        
        print(f"DEBUG SS BTBCTF - Date: {policy_date}, State: {state_code}, Body: {body_type}, Business: {business_use_type}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_btbctf
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND business_use_type = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, business_use_type))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS BTBCTF - Found trailer factor: {factor}")
        else:
            print(f"DEBUG SS BTBCTF - No trailer factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS BTBCTF Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- SS (Non Admitted) MODEL YEAR FACTOR ENDPOINT ---
@app.route("/rate/ss_model_year_factor", methods=["POST"])
def rate_ss_model_year_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        vehicle_class = data.get("vehicle_class")
        vehicle_year = int(data.get("vehicle_year", 0))
        non_owned_trailer = data.get("non_owned_trailer", False)
        
        print(f"DEBUG SS Model Year - Date: {policy_date}, State: {state_code}, Body: {body_type}, Class: {vehicle_class}, Year: {vehicle_year}, NonOwned: {non_owned_trailer}")
        
        # Default to 1.0 for Non Owned Trailers
        if non_owned_trailer:
            print(f"DEBUG SS Model Year - Non Owned Trailer, returning 1.0")
            return jsonify({"factor": "1.0"})
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_model_year_factor
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND vehicle_class = %s
              AND minimum_year <= %s
              AND maximum_year >= %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, vehicle_class, vehicle_year, vehicle_year))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS Model Year - Found factor: {factor}")
        else:
            print(f"DEBUG SS Model Year - No factor found for year {vehicle_year}, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS Model Year Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- SS (Non Admitted) MODEL YEAR TRAILER FACTOR ENDPOINT ---
@app.route("/rate/ss_model_year_trailer_factor", methods=["POST"])
def rate_ss_model_year_trailer_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        vehicle_year = int(data.get("vehicle_year", 0))
        non_owned_trailer = data.get("non_owned_trailer", False)
        
        print(f"DEBUG SS Model Year Trailer - Date: {policy_date}, State: {state_code}, Body: {body_type}, Year: {vehicle_year}, NonOwned: {non_owned_trailer}")
        
        # Default to 1.0 for Non Owned Trailers
        if non_owned_trailer:
            print(f"DEBUG SS Model Year Trailer - Non Owned Trailer, returning 1.0")
            return jsonify({"factor": "1.0"})
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_model_year_trailer_factor
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND minimum_year <= %s
              AND maximum_year >= %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, vehicle_year, vehicle_year))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS Model Year Trailer - Found factor: {factor}")
        else:
            print(f"DEBUG SS Model Year Trailer - No factor found for year {vehicle_year}, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS Model Year Trailer Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- SS (Non Admitted) ILF POWER UNIT FACTOR ENDPOINT ---
@app.route("/rate/ss_ilf_power_unit_factor", methods=["POST"])
def rate_ss_ilf_power_unit_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        vehicle_class = data.get("vehicle_class")
        al_limit = int(data.get("al_limit", 0))
        
        print(f"DEBUG SS ILF Power Unit - Date: {policy_date}, State: {state_code}, Body: {body_type}, Class: {vehicle_class}, Limit: {al_limit}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_ilf_power_unit
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND vehicle_class = %s
              AND al_limit = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, vehicle_class, al_limit))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS ILF Power Unit - Found factor: {factor}")
        else:
            print(f"DEBUG SS ILF Power Unit - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS ILF Power Unit Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) ILF TRAILER FACTOR ENDPOINT ---
@app.route("/rate/ss_ilf_trailer_factor", methods=["POST"])
def rate_ss_ilf_trailer_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        body_type = data.get("body_type")
        al_limit = int(data.get("al_limit", 0))
        
        print(f"DEBUG SS ILF Trailer - Date: {policy_date}, State: {state_code}, Body: {body_type}, Limit: {al_limit}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_ilf_trailer
            WHERE effective_date <= %s 
              AND state_code = %s
              AND body_type = %s
              AND al_limit = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, body_type, al_limit))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS ILF Trailer - Found factor: {factor}")
        else:
            print(f"DEBUG SS ILF Trailer - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS ILF Trailer Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- SS (Non Admitted) USDOT FACTOR ENDPOINT ---
@app.route("/rate/ss_usdot_factor", methods=["POST"])
def rate_ss_usdot_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        usdot_violations = int(data.get("usdot_violations", 0))
        
        print(f"DEBUG SS USDOT Factor - Date: {policy_date}, State: {state_code}, Violations: {usdot_violations}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_usdot_factor
            WHERE effective_date <= %s 
              AND state_code = %s
              AND min_usdot_violations <= %s
              AND max_usdot_violations >= %s
            ORDER BY effective_date DESC, min_usdot_violations DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, usdot_violations, usdot_violations))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS USDOT Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS USDOT Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS USDOT Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- SS (Non Admitted) USDOT BASIC FACTOR ENDPOINT ---
@app.route("/rate/ss_usdot_basic_factor", methods=["POST"])
def rate_ss_usdot_basic_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        usdot_violations = int(data.get("usdot_violations", 0))
        basic_violations = int(data.get("basic_violations", 0))
        
        print(f"DEBUG SS USDOT Basic Factor - Date: {policy_date}, State: {state_code}, USDOT: {usdot_violations}, Basic: {basic_violations}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_usdot_basic_factor
            WHERE effective_date <= %s 
              AND state_code = %s
              AND min_usdot_violations <= %s
              AND max_usdot_violations >= %s
              AND min_basic_violations <= %s
              AND max_basic_violations >= %s
            ORDER BY effective_date DESC, min_usdot_violations DESC, min_basic_violations DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, usdot_violations, usdot_violations, basic_violations, basic_violations))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS USDOT Basic Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS USDOT Basic Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS USDOT Basic Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- SS (Non Admitted) FLEET SIZE FACTOR ENDPOINT ---
@app.route("/rate/ss_fleet_size_factor", methods=["POST"])
def rate_ss_fleet_size_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        num_power_units = int(data.get("num_power_units", 0))
        
        print(f"DEBUG SS Fleet Size Factor - Date: {policy_date}, State: {state_code}, Power Units: {num_power_units}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM ss_fleet_size_factor
            WHERE effective_date <= %s 
              AND state_code = %s
              AND min_fleet <= %s
              AND max_fleet >= %s
            ORDER BY effective_date DESC, min_fleet DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code, num_power_units, num_power_units))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG SS Fleet Size Factor - Found factor: {factor}")
        else:
            print(f"DEBUG SS Fleet Size Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": str(factor)})
    except Exception as e:
        print(f"SS Fleet Size Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/rate/ss_yib_factor', methods=['POST'])
def get_ss_yib_factor():
    """
    Get Non Admitted Years in Business factor
    Applies to both power units and trailers
    """
    try:
        data = request.get_json()
        effective_date = data.get('effective_date')
        state_code = data.get('state_code')
        years_in_business = data.get('years_in_business')
        
        if not all([effective_date, state_code, years_in_business is not None]):
            return jsonify({
                'error': 'Missing required fields: effective_date, state_code, years_in_business'
            }), 400
        
        # Convert years_in_business to integer
        years_in_business = int(years_in_business)
        
        query = """
            SELECT factor
            FROM ss_yib_factor
            WHERE state_code = %s
              AND effective_date <= %s
              AND minimum_years <= %s
              AND (maximum_years >= %s OR maximum_years IS NULL)
            ORDER BY effective_date DESC
            LIMIT 1
        """
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query, (state_code, effective_date, years_in_business, years_in_business))
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result:
            return jsonify({
                'state_code': state_code,
                'years_in_business': years_in_business,
                'factor': float(result[0])
            })
        else:
            return jsonify({
                'error': f'No YIB factor found for state {state_code}, effective date {effective_date}, years {years_in_business}'
            }), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# --- SS (Non Admitted) LOSS HISTORY FACTOR ENDPOINT ---
@app.route('/rate/ss_loss_history_factor', methods=['POST'])
def get_ss_loss_history_factor():
    try:
        data = request.json
        effective_date = str(data.get('effective_date'))
        state_code = str(data.get('state_code'))
        total_claims_paid = float(data.get('total_claims_paid', 0))  # Changed from total_losses
        num_vehicles = int(data.get('num_vehicles', 1))
        
        print(f"DEBUG - SS Loss History: date={effective_date}, state={state_code}, claims_paid={total_claims_paid}, vehicles={num_vehicles}")
        
        if not all([effective_date, state_code]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query for loss history factor based on total claims paid
        query = """
            SELECT factor 
            FROM ss_loss_history 
            WHERE effective_date <= %s 
            AND state_code = %s 
            AND %s BETWEEN min_losses AND max_losses
            ORDER BY effective_date DESC
            LIMIT 1
        """
        
        cursor.execute(query, (effective_date, state_code, total_claims_paid))
        result = cursor.fetchone()
        
        if result:
            table_factor = float(result[0])
            print(f"DEBUG - Found table factor: {table_factor}")
        else:
            table_factor = 0.0
            print(f"DEBUG - No match found, using default table factor 0.0")
        
        cursor.close()
        conn.close()
        
        # Calculate: (table_factor / num_vehicles) + 1
        loss_history_factor = (table_factor / num_vehicles) + 1 if num_vehicles > 0 else 1.0
        
        print(f"DEBUG - Final loss history factor: {loss_history_factor}")
        
        return jsonify({
            'loss_history_factor': round(loss_history_factor, 4)
        })
        
    except Exception as e:
        print(f"ERROR in SS loss history factor: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
# --- DRIVER CLASS FACTOR SS    

@app.route('/rate/ss_driver_class_factor', methods=['POST'])
def get_ss_driver_class_factor():
    try:
        data = request.json
        effective_date = data.get('effective_date')
        state_code = data.get('state_code')
        drivers = data.get('drivers')
        
        print(f"DEBUG - Received data: effective_date={effective_date}, state_code={state_code}")
        print(f"DEBUG - Drivers: {drivers}")
        
        if not all([effective_date, state_code, drivers]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Create database connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        driver_factors = []
        
        for i, driver in enumerate(drivers):
            age = driver.get('age')
            accidents = driver.get('accidents', 0)
            violations = driver.get('violations', 0)
            points = accidents + violations
            
            print(f"DEBUG - Driver {i+1}: age={age}, accidents={accidents}, violations={violations}, points={points}")
            
            # Query for driver's factor
            query = """
                SELECT factor 
                FROM ss_driver_class 
                WHERE effective_date <= %s
                AND state_code = %s 
                AND %s BETWEEN min_points AND max_points
                AND %s BETWEEN min_age AND max_age
                ORDER BY effective_date DESC 
                LIMIT 1
            """
            
            print(f"DEBUG - Executing query with: date={effective_date}, state={state_code}, points={points}, age={age}")
            
            cursor.execute(query, (effective_date, state_code, points, age))
            result = cursor.fetchone()
            
            if result:
                factor = result[0]
                print(f"DEBUG - Found factor: {factor}")
            else:
                factor = 1.0
                print(f"DEBUG - No match found, using default 1.0")
            
            driver_factors.append(factor)
        
        # Close database connection
        cursor.close()
        conn.close()
        
        # Average all driver factors
        avg_driver_factor = sum(driver_factors) / len(driver_factors) if driver_factors else 1.0
        
        print(f"DEBUG - Individual factors: {driver_factors}")
        print(f"DEBUG - Average factor: {avg_driver_factor}")
        
        return jsonify({
            'driver_class_factor': round(avg_driver_factor, 4),
            'individual_factors': driver_factors
        })
        
    except Exception as e:
        print(f"ERROR in driver class factor: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
# --- SS DRIVER EXPERIENCE ---
    
@app.route('/rate/ss_driver_experience_factor', methods=['POST'])
def get_ss_driver_experience_factor():
    try:
        data = request.json
        effective_date = str(data.get('effective_date'))
        state_code = str(data.get('state_code'))
        drivers = data.get('drivers')  # List of driver objects with experience
        
        print(f"DEBUG - Received data: effective_date={effective_date}, state_code={state_code}")
        print(f"DEBUG - Drivers: {drivers}")
        
        if not all([effective_date, state_code, drivers]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Create database connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        driver_factors = []
        
        for i, driver in enumerate(drivers):
            experience = driver.get('experience', 0)
            
            print(f"DEBUG - Driver {i+1}: experience={experience}")
            
            # Query for driver's experience factor
            query = """
                SELECT factor 
                FROM ss_driver_experience 
                WHERE effective_date <= %s 
                AND state_code = %s 
                AND %s BETWEEN min_exp AND max_exp
                ORDER BY effective_date DESC
                LIMIT 1
            """
            
            print(f"DEBUG - Executing query with: date={effective_date}, state={state_code}, experience={experience}")
            
            cursor.execute(query, (effective_date, state_code, experience))
            result = cursor.fetchone()
            
            if result:
                factor = result[0]
                print(f"DEBUG - Found factor: {factor}")
            else:
                factor = 1.0
                print(f"DEBUG - No match found, using default 1.0")
            
            driver_factors.append(factor)
        
        # Close database connection
        cursor.close()
        conn.close()
        
        # Average all driver factors
        avg_driver_factor = sum(driver_factors) / len(driver_factors) if driver_factors else 1.0
        
        print(f"DEBUG - Individual factors: {driver_factors}")
        print(f"DEBUG - Average factor: {avg_driver_factor}")
        
        return jsonify({
            'driver_experience_factor': round(avg_driver_factor, 4),
            'individual_factors': driver_factors
        })
        
    except Exception as e:
            print(f"ERROR in driver experience factor: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

# --- APD VEHICLE VALUE FACTOR ENDPOINT ---
@app.route("/rate/apd_vehicle_value_factor", methods=["POST"])
def rate_apd_vehicle_value_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        vehicle_value = float(data.get("vehicle_value", 0))
        
        print(f"DEBUG APD Vehicle Value Factor - Date: {policy_date}, Value: {vehicle_value}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM apd_vehicle_value_factor
            WHERE effective_date <= %s 
              AND min_value <= %s
              AND max_value >= %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, vehicle_value, vehicle_value))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG APD Vehicle Value Factor - Found factor: {factor}")
        else:
            print(f"DEBUG APD Vehicle Value Factor - No factor found for value {vehicle_value}, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": float(factor)})
    except Exception as e:
        print(f"APD Vehicle Value Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- APD RATE FACTOR CLASS ENDPOINT ---
@app.route("/rate/apd_rate_factor_class", methods=["POST"])
def rate_apd_rate_factor_class():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        vehicle_class = data.get("vehicle_class")
        
        print(f"DEBUG APD Rate Factor Class - Date: {policy_date}, Class: {vehicle_class}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM apd_rate_factor_class
            WHERE effective_date <= %s 
              AND vehicle_class = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, vehicle_class))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG APD Rate Factor Class - Found factor: {factor}")
        else:
            print(f"DEBUG APD Rate Factor Class - No factor found for class {vehicle_class}, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": float(factor)})
    except Exception as e:
        print(f"APD Rate Factor Class Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
@app.route("/rate/apd_vehicle_age_factor", methods=["POST"])
def rate_apd_vehicle_age_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        vehicle_year = int(data.get("vehicle_year", 0))
        
        # Calculate vehicle age from current year
        from datetime import datetime
        policy_year = datetime.strptime(policy_date, '%Y-%m-%d').year
        vehicle_age = policy_year - vehicle_year
        
        print(f"DEBUG APD Vehicle Age Factor - Date: {policy_date}, Vehicle Year: {vehicle_year}, Age: {vehicle_age}")
        
        factor = Decimal('1.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM apd_vehicle_age_factor
            WHERE effective_date <= %s 
              AND vehicle_age_min <= %s
              AND vehicle_age_max >= %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, vehicle_age, vehicle_age))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG APD Vehicle Age Factor - Found factor: {factor}")
        else:
            print(f"DEBUG APD Vehicle Age Factor - No factor found for age {vehicle_age}, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": float(factor), "vehicle_age": vehicle_age})
    except Exception as e:
        print(f"APD Vehicle Age Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- APD OOS FACTOR (USDOT Violations) ENDPOINT ---
@app.route("/rate/apd_oos_factor", methods=["POST"])
def rate_apd_oos_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        violations = int(data.get("violations", 0))
        
        print(f"DEBUG APD OOS Factor - Date: {policy_date}, Violations: {violations}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM apd_oos_factor
            WHERE effective_date <= %s 
              AND violations = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, violations))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG APD OOS Factor - Found factor: {factor}")
        else:
            print(f"DEBUG APD OOS Factor - No factor found for {violations} violations, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": float(factor)})
    except Exception as e:
        print(f"APD OOS Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- APD DEDUCTIBLE FACTOR ENDPOINT ---
@app.route("/rate/apd_deductible_factor", methods=["POST"])
def rate_apd_deductible_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        deductible = int(data.get("deductible", 0))
        
        print(f"DEBUG APD Deductible Factor - Date: {policy_date}, Deductible: {deductible}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM apd_deductible_factor
            WHERE effective_date <= %s 
              AND deductible = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, deductible))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG APD Deductible Factor - Found factor: {factor}")
        else:
            print(f"DEBUG APD Deductible Factor - No factor found for deductible {deductible}, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": float(factor)})
    except Exception as e:
        print(f"APD Deductible Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- APD RADIUS FACTOR ENDPOINT ---
@app.route("/rate/apd_radius_factor", methods=["POST"])
def rate_apd_radius_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        radius_0_50 = float(data.get("radius_0_50", 0))
        radius_51_200 = float(data.get("radius_51_200", 0))
        radius_201_500 = float(data.get("radius_201_500", 0))
        radius_501_plus = float(data.get("radius_501_plus", 0))
        
        print(f"DEBUG APD Radius Factor - Date: {policy_date}")
        print(f"  Radius 0-50: {radius_0_50}%")
        print(f"  Radius 51-200: {radius_51_200}%")
        print(f"  Radius 201-500: {radius_201_500}%")
        print(f"  Radius 501+: {radius_501_plus}%")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Fetch all radius factors for the effective date
        sql = """
            SELECT radius_category, factor FROM apd_radius_factor
            WHERE effective_date <= %s
            ORDER BY effective_date DESC
            LIMIT 4;
        """
        cur.execute(sql, (policy_date,))
        results = cur.fetchall()
        
        # Build a dictionary of factors by radius category
        factors = {}
        for row in results:
            factors[row[0]] = float(row[1])
        
        print(f"DEBUG APD Radius Factor - Found factors: {factors}")
        
        # Calculate weighted factor
        weighted_factor = (
            (radius_0_50 / 100.0) * factors.get('0-50', 1.0) +
            (radius_51_200 / 100.0) * factors.get('51-200', 1.0) +
            (radius_201_500 / 100.0) * factors.get('201-500', 1.0) +
            (radius_501_plus / 100.0) * factors.get('501+', 1.0)
        )
        
        print(f"DEBUG APD Radius Factor - Weighted Factor: {weighted_factor}")
        
        cur.close()
        conn.close()
        
        return jsonify({"weighted_factor": float(weighted_factor)})
    except Exception as e:
        print(f"APD Radius Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- APD ZIP POPULATION DENSITY LOOKUP ENDPOINT ---
@app.route("/lookup/apd_zip_density", methods=["POST"])
def lookup_apd_zip_density():
    try:
        data = request.json
        zip_code = data.get("zip_code")
        
        print(f"DEBUG APD Zip Density - Zip: {zip_code}")
        
        density = None
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT density FROM apd_zip_population_density
            WHERE zip_code = %s;
        """
        cur.execute(sql, (zip_code,))
        result = cur.fetchone()
        
        if result:
            density = float(result[0])
            print(f"DEBUG APD Zip Density - Found density: {density}")
        else:
            print(f"DEBUG APD Zip Density - No density found for zip {zip_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"density": density})
    except Exception as e:
        print(f"APD Zip Density Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- APD POPULATION DENSITY FACTOR ENDPOINT ---
@app.route("/rate/apd_population_density_factor", methods=["POST"])
def rate_apd_population_density_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        zip_code = data.get("zip_code")
        
        print(f"DEBUG APD Population Density Factor - Date: {policy_date}, Zip: {zip_code}")
        
        # First, lookup the density for this zip code
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql_density = """
            SELECT density FROM apd_zip_population_density
            WHERE zip_code = %s;
        """
        cur.execute(sql_density, (zip_code,))
        density_result = cur.fetchone()
        
        if density_result:
            density = float(density_result[0])
            print(f"DEBUG APD Population Density Factor - Found density: {density}")
        else:
            # Zip code not found, use default factor 1.49
            print(f"DEBUG APD Population Density Factor - Zip not found, using default factor 1.49")
            cur.close()
            conn.close()
            return jsonify({"factor": 1.49, "density": None})
        
        # Now lookup the factor based on density range
        sql_factor = """
            SELECT factor FROM apd_population_density_factor
            WHERE effective_date <= %s 
              AND density_min <= %s
            ORDER BY effective_date DESC, density_min DESC
            LIMIT 1;
        """
        cur.execute(sql_factor, (policy_date, density))
        factor_result = cur.fetchone()
        
        if factor_result:
            factor = float(factor_result[0])
            print(f"DEBUG APD Population Density Factor - Found factor: {factor}")
        else:
            # No factor found for this density, use default
            factor = 1.49
            print(f"DEBUG APD Population Density Factor - No factor found, using default 1.49")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": factor, "density": density})
    except Exception as e:
        print(f"APD Population Density Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- APD STATE FACTOR ENDPOINT ---
@app.route("/rate/apd_state_factor", methods=["POST"])
def rate_apd_state_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG APD State Factor - Date: {policy_date}, State: {state_code}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM apd_state_factor
            WHERE effective_date <= %s 
              AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG APD State Factor - Found factor: {factor}")
        else:
            print(f"DEBUG APD State Factor - No factor found for state {state_code}, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": float(factor)})
    except Exception as e:
        print(f"APD State Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- APD YIB FACTOR ENDPOINT ---
@app.route("/rate/apd_yib_factor", methods=["POST"])
def rate_apd_yib_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        years_in_business = int(data.get("years_in_business", 0))
        
        print(f"DEBUG APD YIB Factor - Date: {policy_date}, Years: {years_in_business}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM apd_yib_factor
            WHERE effective_date <= %s 
              AND min_years <= %s
              AND max_years >= %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, years_in_business, years_in_business))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG APD YIB Factor - Found factor: {factor}")
        else:
            print(f"DEBUG APD YIB Factor - No factor found for {years_in_business} years, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": float(factor)})
    except Exception as e:
        print(f"APD YIB Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- APD FLEET SIZE FACTOR ENDPOINT ---
@app.route("/rate/apd_fleet_size_factor", methods=["POST"])
def rate_apd_fleet_size_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        num_power_units = int(data.get("num_power_units", 0))
        
        print(f"DEBUG APD Fleet Size Factor - Date: {policy_date}, Power Units: {num_power_units}")
        
        factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor FROM apd_fleet_size
            WHERE effective_date <= %s 
              AND min_fleet <= %s
              AND max_fleet >= %s
            ORDER BY effective_date DESC, min_fleet DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, num_power_units, num_power_units))
        result = cur.fetchone()
        
        if result:
            factor = result[0]
            print(f"DEBUG APD Fleet Size Factor - Found factor: {factor}")
        else:
            print(f"DEBUG APD Fleet Size Factor - No factor found for {num_power_units} power units, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"factor": float(factor)})
    except Exception as e:
        print(f"APD Fleet Size Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- APD DRIVER AGE FACTOR ENDPOINT ---
@app.route("/rate/apd_driver_age_factor", methods=["POST"])
def rate_apd_driver_age_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        drivers = data.get("drivers", [])
        
        print(f"DEBUG APD Driver Age Factor - Date: {policy_date}, Drivers: {len(drivers)}")
        
        if not drivers:
            print("DEBUG APD Driver Age Factor - No drivers provided, using default 1.0")
            return jsonify({"driver_age_factor": 1.0, "individual_factors": []})
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        driver_factors = []
        
        for i, driver in enumerate(drivers):
            age = driver.get('age', 0)
            
            if age > 0:
                sql = """
                    SELECT factor 
                    FROM apd_driver_age
                    WHERE effective_date <= %s 
                      AND min_age <= %s
                      AND max_age >= %s
                    ORDER BY effective_date DESC, min_age DESC
                    LIMIT 1;
                """
                cur.execute(sql, (policy_date, age, age))
                result = cur.fetchone()
                
                if result:
                    factor = float(result[0])
                    print(f"DEBUG APD Driver Age Factor - Driver {i+1} (age {age}): {factor}")
                else:
                    factor = 1.0
                    print(f"DEBUG APD Driver Age Factor - Driver {i+1} (age {age}): No factor found, using 1.0")
                
                driver_factors.append(factor)
        
        cur.close()
        conn.close()
        
        # Calculate average of all driver factors
        avg_driver_factor = sum(driver_factors) / len(driver_factors) if driver_factors else 1.0
        
        print(f"DEBUG APD Driver Age Factor - Average: {avg_driver_factor}")
        
        return jsonify({
            "driver_age_factor": round(avg_driver_factor, 4),
            "individual_factors": driver_factors
        })
    except Exception as e:
        print(f"APD Driver Age Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- APD DRIVER EXPERIENCE FACTOR ENDPOINT ---
@app.route("/rate/apd_driver_experience_factor", methods=["POST"])
def rate_apd_driver_experience_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        drivers = data.get("drivers", [])
        
        print(f"DEBUG APD Driver Experience Factor - Date: {policy_date}, Drivers: {len(drivers)}")
        
        if not drivers:
            print("DEBUG APD Driver Experience Factor - No drivers provided, using default 1.0")
            return jsonify({"driver_experience_factor": 1.0, "individual_factors": []})
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        driver_factors = []
        
        for i, driver in enumerate(drivers):
            experience = driver.get('experience', 0)
            
            sql = """
                SELECT factor 
                FROM apd_driver_experience
                WHERE effective_date <= %s 
                  AND min_experience <= %s
                  AND max_experience >= %s
                ORDER BY effective_date DESC, min_experience DESC
                LIMIT 1;
            """
            cur.execute(sql, (policy_date, experience, experience))
            result = cur.fetchone()
            
            if result:
                factor = float(result[0])
                print(f"DEBUG APD Driver Experience Factor - Driver {i+1} (experience {experience}): {factor}")
            else:
                factor = 1.0
                print(f"DEBUG APD Driver Experience Factor - Driver {i+1} (experience {experience}): No factor found, using 1.0")
            
            driver_factors.append(factor)
        
        cur.close()
        conn.close()
        
        # Calculate average of all driver factors
        avg_driver_factor = sum(driver_factors) / len(driver_factors) if driver_factors else 1.0
        
        print(f"DEBUG APD Driver Experience Factor - Average: {avg_driver_factor}")
        
        return jsonify({
            "driver_experience_factor": round(avg_driver_factor, 4),
            "individual_factors": driver_factors
        })
    except Exception as e:
        print(f"APD Driver Experience Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- APD DRIVER VIOLATIONS FACTOR ENDPOINT ---
@app.route("/rate/apd_driver_violations_factor", methods=["POST"])
def rate_apd_driver_violations_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        drivers = data.get("drivers", [])
        
        print(f"DEBUG APD Driver Violations Factor - Date: {policy_date}, Drivers: {len(drivers)}")
        
        if not drivers:
            print("DEBUG APD Driver Violations Factor - No drivers provided, using default 1.0")
            return jsonify({"driver_violations_factor": 1.0, "total_violations": 0})
        
        # Calculate total violations across all drivers
        total_violations = sum(driver.get('violations', 0) for driver in drivers)
        num_drivers = len(drivers)
        
        # Formula: ((Total Violations Ã— 0.15) / Number of Drivers) + 1
        factor = ((total_violations * 0.15) / num_drivers) + 1.0
        
        print(f"DEBUG APD Driver Violations - Total Violations: {total_violations}")
        print(f"DEBUG APD Driver Violations - Number of Drivers: {num_drivers}")
        print(f"DEBUG APD Driver Violations - Calculation: (({total_violations} Ã— 0.15) / {num_drivers}) + 1 = {factor}")
        
        return jsonify({
            "driver_violations_factor": round(factor, 4),
            "total_violations": total_violations,
            "num_drivers": num_drivers
        })
    except Exception as e:
        print(f"APD Driver Violations Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- APD MINIMUM PREMIUM PER VEHICLE ENDPOINT ---
@app.route("/rate/apd_minimum_premium_per_vehicle", methods=["POST"])
def rate_apd_minimum_premium_per_vehicle():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        
        print(f"DEBUG APD Min Premium Per Vehicle - Date: {policy_date}")
        
        minimum_premium = Decimal('750.0')  # Default
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT minimum_premium FROM apd_mp_per_vehicle
            WHERE effective_date <= %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date,))
        result = cur.fetchone()
        
        if result:
            minimum_premium = result[0]
            print(f"DEBUG APD Min Premium Per Vehicle - Found: {minimum_premium}")
        else:
            print(f"DEBUG APD Min Premium Per Vehicle - No minimum found, using default 750")
        
        cur.close()
        conn.close()
        
        return jsonify({"minimum_premium": str(minimum_premium)})
    except Exception as e:
        print(f"APD Minimum Premium Per Vehicle Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    

# MP YEARS IN BUSINESS    
@app.route('/rate/apd_mp_yib', methods=['POST'])
def apd_mp_yib():
    """Get APD Minimum Premium YIB factor based on years in business"""
    try:
        data = request.json
        effective_date = data.get('effective_date')
        years_in_business = data.get('years_in_business', 0)
        
        if not effective_date:
            return jsonify({'error': 'Missing effective_date'}), 400
        
        print(f"DEBUG APD MP YIB - Date: {effective_date}, Years in Business: {years_in_business}")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Find the most recent effective date that is <= policy date
        query = """
            SELECT DISTINCT effective_date 
            FROM apd_mp_yib 
            WHERE effective_date <= %s
            ORDER BY effective_date DESC 
            LIMIT 1
        """
        
        cur.execute(query, (effective_date,))
        result = cur.fetchone()
        
        if not result:
            cur.close()
            conn.close()
            return jsonify({'error': 'No APD MP YIB data found for the given date'}), 404
        
        applicable_date = result[0]
        print(f"DEBUG APD MP YIB - Using effective date: {applicable_date}")
        
        # Look up the factor based on years in business
        query = """
            SELECT factor
            FROM apd_mp_yib
            WHERE effective_date = %s
            AND (
                (min_years <= %s AND (max_years IS NULL OR max_years >= %s))
                OR min_years = 99
            )
            ORDER BY 
                CASE WHEN min_years = 99 THEN 1 ELSE 0 END,
                min_years DESC
            LIMIT 1
        """
        
        cur.execute(query, (applicable_date, years_in_business, years_in_business))
        result = cur.fetchone()
        
        if not result:
            # If no match found and years >= 5, try to get the 5+ bracket
            cur.execute("""
                SELECT factor
                FROM apd_mp_yib
                WHERE effective_date = %s
                AND min_years = 5
                AND max_years IS NULL
            """, (applicable_date,))
            result = cur.fetchone()
            
            if not result:
                # Last resort: get the 99 (unknown) factor
                cur.execute("""
                    SELECT factor
                    FROM apd_mp_yib
                    WHERE effective_date = %s
                    AND min_years = 99
                """, (applicable_date,))
                result = cur.fetchone()
        
        if not result:
            cur.close()
            conn.close()
            return jsonify({'error': 'No APD MP YIB factor found'}), 404
        
        factor = float(result[0])
        print(f"DEBUG APD MP YIB - Factor found: {factor}")
        
        cur.close()
        conn.close()
        
        return jsonify({
            'factor': factor,
            'years_in_business': years_in_business,
            'effective_date': str(applicable_date)
        })
        
    except Exception as e:
        print(f"Error in apd_mp_yib: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
# Fees Taxability ---
@app.route("/get/fees_taxability", methods=["POST"])
def get_fees_taxability():
    print("=== FEES TAXABILITY ENDPOINT CALLED ===")
    try:
        data = request.json
        state_code = data.get("state_code")
        print(f"State Code: {state_code}")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT coverage_type, uw_fee_taxability, broker_fee_taxability, policy_fee_taxability
            FROM fees_taxability
            WHERE state_code = %s;
        """
        cur.execute(sql, (state_code,))
        results = cur.fetchall()
        
        print(f"Found {len(results)} rows")
        
        taxability_list = []
        for row in results:
            taxability_list.append({
                "coverage_type": row[0],
                "uw_fee_taxability": row[1],
                "broker_fee_taxability": row[2],
                "policy_fee_taxability": row[3]
            })
        
        cur.close()
        conn.close()
        
        print(f"Returning: {taxability_list}")
        return jsonify(taxability_list)
    except Exception as e:
        print(f"Fees Taxability Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- POLICY FEE LOOKUP ENDPOINT ---
@app.route("/get/policy_fee", methods=["POST"])
def get_policy_fee():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        coverage = data.get("coverage")  # AL, APD, MTC, TGL, NTL
        
        fee = Decimal('0.0')
        taxable = False
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT fee, taxable FROM policy_fees
            WHERE effective_date <= %s
              AND state_code = %s
              AND coverage = %s
            ORDER BY effective_date DESC LIMIT 1;
        """
        
        cur.execute(sql, (policy_date, state_code, coverage))
        result = cur.fetchone()
        
        if result:
            fee = result[0]
            taxable = result[1]
        
        cur.close()
        conn.close()
        
        return jsonify({
            "fee": str(fee),
            "taxable": taxable
        })
        
    except Exception as e:
        print(f"Policy Fee Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- APD DRIVER CRASHES FACTOR ENDPOINT ---
@app.route("/rate/apd_driver_crashes_factor", methods=["POST"])
def rate_apd_driver_crashes_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        drivers = data.get("drivers", [])
        
        print(f"DEBUG APD Driver Crashes Factor - Date: {policy_date}, Drivers: {len(drivers)}")
        
        if not drivers:
            print("DEBUG APD Driver Crashes Factor - No drivers provided, using default 1.0")
            return jsonify({"driver_crashes_factor": 1.0, "total_crashes": 0})
        
        # Calculate total crashes across all drivers
        total_crashes = sum(driver.get('crashes', 0) for driver in drivers)
        num_drivers = len(drivers)
        
        # Formula: ((Total Crashes Ã— 0.2) / Number of Drivers) + 1
        factor = ((total_crashes * 0.2) / num_drivers) + 1.0
        
        print(f"DEBUG APD Driver Crashes - Total Crashes: {total_crashes}")
        print(f"DEBUG APD Driver Crashes - Number of Drivers: {num_drivers}")
        print(f"DEBUG APD Driver Crashes - Calculation: (({total_crashes} Ã— 0.2) / {num_drivers}) + 1 = {factor}")
        
        return jsonify({
            "driver_crashes_factor": round(factor, 4),
            "total_crashes": total_crashes,
            "num_drivers": num_drivers
        })
    except Exception as e:
        print(f"APD Driver Crashes Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- APD LOSS FACTOR ENDPOINT ---
@app.route("/rate/apd_loss_factor", methods=["POST"])
def rate_apd_loss_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        loss_ratio_year1 = float(data.get("loss_ratio_year1", 0))
        loss_ratio_year2 = float(data.get("loss_ratio_year2", 0))
        loss_ratio_year3 = float(data.get("loss_ratio_year3", 0))
        
        print(f"DEBUG APD Loss Factor - Date: {policy_date}")
        print(f"  Year 1 Ratio: {loss_ratio_year1:.4f}")
        print(f"  Year 2 Ratio: {loss_ratio_year2:.4f}")
        print(f"  Year 3 Ratio: {loss_ratio_year3:.4f}")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Initialize factors with defaults
        year1_factor = 1.0  # Default for year 1
        year2_factor = 0.0  # Default for year 2
        year3_factor = 0.0  # Default for year 3
        
        # Lookup Year 1 Factor
        if loss_ratio_year1 > 0:
            sql = """
                SELECT year1_factor 
                FROM apd_loss_factor
                WHERE effective_date <= %s 
                  AND min_ratio <= %s
                  AND max_ratio >= %s
                ORDER BY effective_date DESC
                LIMIT 1;
            """
            cur.execute(sql, (policy_date, loss_ratio_year1, loss_ratio_year1))
            result = cur.fetchone()
            if result:
                year1_factor = float(result[0])
                print(f"DEBUG APD Loss Factor - Year 1 Factor: {year1_factor}")
        
        # Lookup Year 2 Factor
        if loss_ratio_year2 > 0:
            sql = """
                SELECT year2_factor 
                FROM apd_loss_factor
                WHERE effective_date <= %s 
                  AND min_ratio <= %s
                  AND max_ratio >= %s
                ORDER BY effective_date DESC
                LIMIT 1;
            """
            cur.execute(sql, (policy_date, loss_ratio_year2, loss_ratio_year2))
            result = cur.fetchone()
            if result:
                year2_factor = float(result[0])
                print(f"DEBUG APD Loss Factor - Year 2 Factor: {year2_factor}")
        
        # Lookup Year 3 Factor
        if loss_ratio_year3 > 0:
            sql = """
                SELECT year3_factor 
                FROM apd_loss_factor
                WHERE effective_date <= %s 
                  AND min_ratio <= %s
                  AND max_ratio >= %s
                ORDER BY effective_date DESC
                LIMIT 1;
            """
            cur.execute(sql, (policy_date, loss_ratio_year3, loss_ratio_year3))
            result = cur.fetchone()
            if result:
                year3_factor = float(result[0])
                print(f"DEBUG APD Loss Factor - Year 3 Factor: {year3_factor}")
        
        cur.close()
        conn.close()
        
        return jsonify({
            "year1_factor": year1_factor,
            "year2_factor": year2_factor,
            "year3_factor": year3_factor
        })
    except Exception as e:
        print(f"APD Loss Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- APD TSL RATE LOOKUP ENDPOINT ---
@app.route("/rate/apd_tsl", methods=["POST"])
def rate_apd_tsl():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        towing_limit = data.get("towing_limit")
        vehicle_type = data.get("vehicle_type")  # 'POWER' or 'TRAILER'
        
        premium = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT premium_per_vehicle FROM apd_tsl
            WHERE effective_date <= %s
              AND towing_limit = %s
              AND vehicle_type = %s
            ORDER BY effective_date DESC LIMIT 1;
        """
        
        cur.execute(sql, (policy_date, towing_limit, vehicle_type))
        result = cur.fetchone()
        
        if result:
            premium = result[0]
        
        cur.close()
        conn.close()
        
        return jsonify({"premium_per_vehicle": str(premium)})
        
    except Exception as e:
        print(f"APD TSL Rate Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- UW FEE RATE LOOKUP ENDPOINT ---
@app.route("/get/uw_fee_rate", methods=["POST"])
def get_uw_fee_rate():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        coverage = data.get("coverage")  # MTC, TGL, or NTL
        
        rate = Decimal('0.0')
        taxable = False
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate, taxable FROM uw_fees
            WHERE effective_date <= %s
              AND state_code = %s
              AND coverage = %s
            ORDER BY effective_date DESC LIMIT 1;
        """
        
        cur.execute(sql, (policy_date, state_code, coverage))
        result = cur.fetchone()
        
        if result:
            rate = result[0]
            taxable = result[1]
        
        cur.close()
        conn.close()
        
        return jsonify({
            "rate": str(rate),
            "taxable": taxable
        })
        
    except Exception as e:
        print(f"UW Fee Rate Error: {e}")
        return jsonify({"error": str(e)}), 500
    
# --- AL UW FEE RATE LOOKUP ENDPOINT ---
@app.route("/get/al_uw_fee_rate", methods=["POST"])
def get_al_uw_fee_rate():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        telematics_type = data.get("telematics_type", "NONE")  # Default to NONE if not provided
        
        rate = Decimal('0.0')
        taxable = False
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate, taxable FROM al_uw_fees
            WHERE effective_date <= %s
              AND state_code = %s
              AND coverage = 'AL'
              AND telematics_type = %s
            ORDER BY effective_date DESC LIMIT 1;
        """
        
        cur.execute(sql, (policy_date, state_code, telematics_type))
        result = cur.fetchone()
        
        if result:
            rate = result[0]
            taxable = result[1]
        
        cur.close()
        conn.close()
        
        return jsonify({
            "rate": str(rate),
            "taxable": taxable
        })
        
    except Exception as e:
        print(f"AL UW Fee Rate Error: {e}")        
        return jsonify({"error": str(e)}), 500
    
@app.route('/calculate_taxes', methods=['POST'])
def calculate_taxes():
    """
    Calculate taxes for a given premium and coverage
    Expected JSON:
    {
        "state_code": "CA",
        "coverage_type": "AL",
        "premium": 5000.00,
        "effective_date": "2025-05-01"
    }
    """
    try:
        data = request.json
        state_code = data.get('state_code', '').upper()
        coverage_type = data.get('coverage_type', '').upper()
        premium = float(data.get('premium', 0))
        effective_date = data.get('effective_date', datetime.now().strftime('%Y-%m-%d'))
        
        if not state_code or not coverage_type or premium <= 0:
            return jsonify({'error': 'Invalid input parameters'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get applicable taxes for this state/coverage/date
        query = """
            SELECT tax_name, tax_type, tax_rate
            FROM taxes_table
            WHERE state_code = %s
            AND coverage_type = %s
            AND effective_date <= %s
            ORDER BY effective_date DESC
        """
        
        cursor.execute(query, (state_code, coverage_type, effective_date))
        taxes = cursor.fetchall()
        
        if not taxes:
            return jsonify({
                'state_code': state_code,
                'coverage_type': coverage_type,
                'premium': premium,
                'taxes': [],
                'total_tax': 0.00,
                'total_with_taxes': premium
            })
        
        # Calculate each tax
        tax_details = []
        total_tax = 0.00
        taxable_base = premium  # Base for percentage taxes (premium + flat fees)
        
        # First pass: calculate flat fees
        flat_fees = 0.00
        for tax in taxes:
            if tax['tax_type'].upper() == 'FLAT':
                tax_amount = float(tax['tax_rate'])
                flat_fees += tax_amount
                tax_details.append({
                    'tax_name': tax['tax_name'],
                    'tax_type': tax['tax_type'],
                    'tax_rate': float(tax['tax_rate']),
                    'tax_amount': round(tax_amount, 2)
                })
        
        # Update taxable base to include flat fees
        taxable_base = premium + flat_fees
        
        # Second pass: calculate percentage taxes
        for tax in taxes:
            if tax['tax_type'].upper() == 'PERCENTAGE':
                # Percentage rate is stored as whole number (e.g., 3 = 3%)
                tax_rate_decimal = float(tax['tax_rate']) / 100
                tax_amount = taxable_base * tax_rate_decimal
                tax_details.append({
                    'tax_name': tax['tax_name'],
                    'tax_type': tax['tax_type'],
                    'tax_rate': float(tax['tax_rate']),
                    'tax_amount': round(tax_amount, 2)
                })
        
        # Calculate total tax
        total_tax = sum(item['tax_amount'] for item in tax_details)
        total_with_taxes = premium + total_tax
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'state_code': state_code,
            'coverage_type': coverage_type,
            'premium': round(premium, 2),
            'taxes': tax_details,
            'total_tax': round(total_tax, 2),
            'total_with_taxes': round(total_with_taxes, 2)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/calculate_policy_taxes', methods=['POST'])
def calculate_policy_taxes():
    """
    Calculate taxes for multiple coverages on a policy
    Expected JSON:
    {
        "state_code": "CA",
        "effective_date": "2025-05-01",
        "coverages": [
            {"coverage_type": "AL", "premium": 5000.00},
            {"coverage_type": "APD", "premium": 2000.00}
        ]
    }
    """
    try:
        data = request.json
        state_code = data.get('state_code', '').upper()
        effective_date = data.get('effective_date', datetime.now().strftime('%Y-%m-%d'))
        coverages = data.get('coverages', [])
        
        if not state_code or not coverages:
            return jsonify({'error': 'Invalid input parameters'}), 400
        
        policy_results = {
            'state_code': state_code,
            'effective_date': effective_date,
            'coverages': [],
            'total_premium': 0.00,
            'total_tax': 0.00,
            'grand_total': 0.00
        }
        
        conn = get_db_connection()
        
        for coverage in coverages:
            coverage_type = coverage.get('coverage_type', '').upper()
            premium = float(coverage.get('premium', 0))
            
            if premium <= 0:
                continue
            
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get applicable taxes
            query = """
                SELECT tax_name, tax_type, tax_rate
                FROM taxes_table
                WHERE state_code = %s
                AND coverage_type = %s
                AND effective_date <= %s
                ORDER BY effective_date DESC
            """
            
            cursor.execute(query, (state_code, coverage_type, effective_date))
            taxes = cursor.fetchall()
            
            # Calculate taxes for this coverage
            tax_details = []
            taxable_base = premium
            
            # Calculate flat fees first
            flat_fees = 0.00
            for tax in taxes:
                if tax['tax_type'].upper() == 'FLAT':
                    tax_amount = float(tax['tax_rate'])
                    flat_fees += tax_amount
                    tax_details.append({
                        'tax_name': tax['tax_name'],
                        'tax_type': tax['tax_type'],
                        'tax_rate': float(tax['tax_rate']),
                        'tax_amount': round(tax_amount, 2)
                    })
            
            # Update taxable base
            taxable_base = premium + flat_fees
            
            # Calculate percentage taxes
            for tax in taxes:
                if tax['tax_type'].upper() == 'PERCENTAGE':
                    tax_rate_decimal = float(tax['tax_rate']) / 100
                    tax_amount = taxable_base * tax_rate_decimal
                    tax_details.append({
                        'tax_name': tax['tax_name'],
                        'tax_type': tax['tax_type'],
                        'tax_rate': float(tax['tax_rate']),
                        'tax_amount': round(tax_amount, 2)
                    })
            
            coverage_total_tax = sum(item['tax_amount'] for item in tax_details)
            coverage_total = premium + coverage_total_tax
            
            policy_results['coverages'].append({
                'coverage_type': coverage_type,
                'premium': round(premium, 2),
                'taxes': tax_details,
                'total_tax': round(coverage_total_tax, 2),
                'total_with_taxes': round(coverage_total, 2)
            })
            
            policy_results['total_premium'] += premium
            policy_results['total_tax'] += coverage_total_tax
            
            cursor.close()
        
        conn.close()
        
        policy_results['total_premium'] = round(policy_results['total_premium'], 2)
        policy_results['total_tax'] = round(policy_results['total_tax'], 2)
        policy_results['grand_total'] = round(policy_results['total_premium'] + policy_results['total_tax'], 2)
        
        return jsonify(policy_results)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500




# --- RADIUS FACTOR ENDPOINT ---
@app.route("/rate/radius_factor", methods=["POST"])
def rate_radius_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        zip_code = data.get("zip_code")
        
        # Build radius_percentages from individual fields
        radius_percentages = {
            "0-50": float(data.get("radius_0_50", 0)) / 100.0,      # Convert 25 to 0.25
            "51-200": float(data.get("radius_51_200", 0)) / 100.0,
            "201-500": float(data.get("radius_201_500", 0)) / 100.0,
            "501+": float(data.get("radius_501_plus", 0)) / 100.0
        }
        
        print(f"DEBUG Radius Factor - Date: {policy_date}, Zip: {zip_code}, Percentages: {radius_percentages}")
        
        total_radius_factor = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get all radius factors for this zipcode
        sql = """
            SELECT radius_category, factor 
            FROM cw_radius_factor
            WHERE effective_date <= %s 
              AND zip_code = %s
            ORDER BY effective_date DESC;
        """
        cur.execute(sql, (policy_date, zip_code))
        results = cur.fetchall()
        
        if results:
            for row in results:
                radius_category = row[0]
                db_factor = Decimal(str(row[1]))
                user_percentage = Decimal(str(radius_percentages.get(radius_category, 0)))
                
                category_factor = db_factor * user_percentage
                total_radius_factor += category_factor
                
                print(f"DEBUG Radius - {radius_category}: {db_factor} Ã— {user_percentage} = {category_factor}")
            
            print(f"DEBUG Radius - Total Factor: {total_radius_factor}")
        else:
            print(f"DEBUG Radius - No factors found for zip {zip_code}, using 1.0")
            total_radius_factor = Decimal('1.0')
        
        cur.close()
        conn.close()
        
        return jsonify({"weighted_factor": str(total_radius_factor)})  # Changed from "radius_factor"
    except Exception as e:
        print(f"Radius Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- ILF FACTOR ENDPOINT ---
@app.route("/rate/ilf_factor", methods=["POST"])
def rate_ilf_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        al_limit = int(data.get("al_limit", 0))
        
        print(f"DEBUG ILF Factor - Date: {policy_date}, AL Limit: {al_limit}")
        
        ilf_factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT ilf_factor FROM ilf_factor
            WHERE effective_date <= %s 
              AND al_limit = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, al_limit))
        result = cur.fetchone()
        
        if result:
            ilf_factor = result[0]
            print(f"DEBUG ILF Factor - Found factor: {ilf_factor}")
        else:
            print(f"DEBUG ILF Factor - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"ilf_factor": str(ilf_factor)})
    except Exception as e:
        print(f"ILF Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- OOS VIOLATIONS FACTOR ENDPOINT ---
@app.route("/rate/oos_violations_factor", methods=["POST"])
def rate_oos_violations_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        usdot_violations = int(data.get("usdot_violations", 0))
        
        # Cap violations at 3 (max in table)
        if usdot_violations > 3:
            usdot_violations = 3
        
        print(f"DEBUG OOS Violations - Date: {policy_date}, Violations: {usdot_violations}")
        
        rate_factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate_factor FROM oos_violations_factor
            WHERE effective_date <= %s 
              AND usdot_violations = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, usdot_violations))
        result = cur.fetchone()
        
        if result:
            rate_factor = result[0]
            print(f"DEBUG OOS Violations - Found factor: {rate_factor}")
        else:
            print(f"DEBUG OOS Violations - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate_factor": str(rate_factor)})
    except Exception as e:
        print(f"OOS Violations Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- FLEET SIZE FACTOR ENDPOINT ---
@app.route("/rate/fleet_size_factor", methods=["POST"])
def rate_fleet_size_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        num_vehicles = int(data.get("num_vehicles", 0))
        
        print(f"DEBUG Fleet Size - Date: {policy_date}, Vehicles: {num_vehicles}")
        
        rate_factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate_factor FROM fleet_size_factor
            WHERE effective_date <= %s 
              AND min_vehicles <= %s
              AND (max_vehicles >= %s OR max_vehicles = 1000)
            ORDER BY effective_date DESC, min_vehicles DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, num_vehicles, num_vehicles))
        result = cur.fetchone()
        
        if result:
            rate_factor = result[0]
            print(f"DEBUG Fleet Size - Found factor: {rate_factor}")
        else:
            print(f"DEBUG Fleet Size - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate_factor": str(rate_factor)})
    except Exception as e:
        print(f"Fleet Size Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- YEARS IN BUSINESS FACTOR ENDPOINT ---
@app.route("/rate/years_in_business_factor", methods=["POST"])
def rate_years_in_business_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        years_in_business = int(data.get("years_in_business", 0))
        
        print(f"DEBUG Years in Business - Date: {policy_date}, Years: {years_in_business}")
        
        rate_factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate_factor FROM years_in_business_factor
            WHERE effective_date <= %s 
              AND min_years <= %s
              AND (max_years >= %s OR max_years = 999)
            ORDER BY effective_date DESC, min_years DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, years_in_business, years_in_business))
        result = cur.fetchone()
        
        if result:
            rate_factor = result[0]
            print(f"DEBUG Years in Business - Found factor: {rate_factor}")
        else:
            print(f"DEBUG Years in Business - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate_factor": str(rate_factor)})
    except Exception as e:
        print(f"Years in Business Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- WEIGHT CLASS FACTOR ENDPOINT ---
@app.route("/rate/weight_class_factor", methods=["POST"])
def rate_weight_class_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        business_use_type = data.get("business_use_type")
        vehicle_class = data.get("vehicle_class")
        
        print(f"DEBUG Weight Class - Date: {policy_date}, Business: {business_use_type}, Class: {vehicle_class}")
        
        rate_factor = Decimal('1.0')  # Default to 1.0 if not found
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate_factor FROM weight_class_factors
            WHERE effective_date <= %s 
              AND business_use_type = %s 
              AND vehicle_class = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, business_use_type, vehicle_class))
        result = cur.fetchone()
        
        if result:
            rate_factor = result[0]
            print(f"DEBUG Weight Class - Found factor: {rate_factor}")
        else:
            print(f"DEBUG Weight Class - No factor found, using default 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate_factor": str(rate_factor)})
    except Exception as e:
        print(f"Weight Class Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# --- DRIVER AGE RATING ENDPOINT ---
@app.route("/rate/driver_age_factor", methods=["POST"])
def rate_driver_age_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        driver_age = data.get("driver_age")
        
        print(f"DEBUG Driver Age - Date: {policy_date}, Age: {driver_age}")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor 
            FROM cw_driver_age
            WHERE effective_date <= %s 
              AND driver_age = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, driver_age))
        result = cur.fetchone()
        
        if result:
            factor = float(result[0])
            print(f"DEBUG Driver Age - Found factor: {factor}")
        else:
            factor = 1.0
            print(f"DEBUG Driver Age - No factor found, using 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate_factor": factor})
    except Exception as e:
        print(f"Driver Age Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

#--- DRIVER EXPERIENCE RATING ENDPOINT ---
@app.route("/rate/driver_experience_factor", methods=["POST"])
def rate_driver_experience_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        driver_experience = data.get("driver_experience")
        
        print(f"DEBUG Driver Experience - Date: {policy_date}, Experience: {driver_experience}")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor 
            FROM cw_driver_experience
            WHERE effective_date <= %s 
              AND driver_experience = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, driver_experience))
        result = cur.fetchone()
        
        if result:
            factor = float(result[0])
            print(f"DEBUG Driver Experience - Found factor: {factor}")
        else:
            factor = 1.0
            print(f"DEBUG Driver Experience - No factor found, using 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate_factor": factor})
    except Exception as e:
        print(f"Driver Experience Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

#--- Driver Crashes Endpoint ---
@app.route("/rate/driver_crashes_factor", methods=["POST"])
def rate_driver_crashes_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        accidents = data.get("accidents")
        
        print(f"DEBUG Driver Crashes - Date: {policy_date}, Accidents: {accidents}")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor 
            FROM cw_driver_crashes
            WHERE effective_date <= %s 
              AND accidents = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, accidents))
        result = cur.fetchone()
        
        if result:
            factor = float(result[0])
            print(f"DEBUG Driver Crashes - Found factor: {factor}")
        else:
            factor = 1.0
            print(f"DEBUG Driver Crashes - No factor found, using 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate_factor": factor})
    except Exception as e:
        print(f"Driver Crashes Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- DRIVER VIOLATION ENDPOINT ---
@app.route("/rate/driver_violations_factor", methods=["POST"])
def rate_driver_violations_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        violations = data.get("violations")
        
        print(f"DEBUG Driver Violations - Date: {policy_date}, Violations: {violations}")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor 
            FROM cw_driver_violations
            WHERE effective_date <= %s 
              AND violations = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, violations))
        result = cur.fetchone()
        
        if result:
            factor = float(result[0])
            print(f"DEBUG Driver Violations - Found factor: {factor}")
        else:
            factor = 1.0
            print(f"DEBUG Driver Violations - No factor found, using 1.0")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate_factor": factor})
    except Exception as e:
        print(f"Driver Violations Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- LOSS HISTORY FACTOR ENDPOINT ---
@app.route("/rate/loss_history_factor", methods=["POST"])
def rate_loss_history_factor():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        total_claims_paid = int(data.get("total_claims_paid", 0))  # Changed variable name
        num_vehicles = int(data.get("num_vehicles", 1))
        
        print(f"DEBUG Loss History - Date: {policy_date}, Total Claims: {total_claims_paid}, Vehicles: {num_vehicles}")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT factor 
            FROM cw_loss_factor
            WHERE effective_date <= %s 
              AND losses = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, total_claims_paid))  # Changed here
        result = cur.fetchone()
        
        if result:
            table_factor = Decimal(str(result[0]))
            print(f"DEBUG Loss History - Table factor for {total_claims_paid} claims: {table_factor}")
        else:
            table_factor = Decimal('0.0')
            print(f"DEBUG Loss History - No factor found for {total_claims_paid} claims, using 0.0")
        
        cur.close()
        conn.close()
        
        loss_history_factor = (table_factor / Decimal(str(num_vehicles))) + Decimal('1.0')
        
        print(f"DEBUG Loss History - Final factor: ({table_factor} / {num_vehicles}) + 1 = {loss_history_factor}")
        
        return jsonify({
            "loss_history_factor": str(loss_history_factor),
            "table_factor": str(table_factor)
        })
    except Exception as e:
        print(f"Loss History Factor Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
    # --- MINIMUM PREMIUM ENDPOINT ---
@app.route("/rate/minimum_premium", methods=["POST"])
def rate_minimum_premium():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        vehicle_class = data.get("vehicle_class")
        al_limit = int(data.get("al_limit", 0))
        radius_percentages = data.get("radius_percentages", {})
        schedule_mod = Decimal(str(data.get("schedule_mod", 1.0)))
        
        print(f"DEBUG Minimum Premium - Date: {policy_date}, Class: {vehicle_class}, Limit: {al_limit}")
        
        total_weighted_minimum = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get minimum premium for each radius category
        for radius_category, user_percentage in radius_percentages.items():
            sql = """
                SELECT minimum_premium 
                FROM cw_minimum_premium
                WHERE effective_date <= %s 
                  AND vehicle_class = %s
                  AND al_limit = %s
                  AND radius_category = %s
                ORDER BY effective_date DESC
                LIMIT 1;
            """
            cur.execute(sql, (policy_date, vehicle_class, al_limit, radius_category))
            result = cur.fetchone()
            
            if result:
                minimum_premium = Decimal(str(result[0]))
                percentage = Decimal(str(user_percentage))
                weighted_amount = minimum_premium * percentage
                total_weighted_minimum += weighted_amount
                
                print(f"DEBUG Minimum Premium - {radius_category}: {minimum_premium} Ã— {percentage} = {weighted_amount}")
            else:
                print(f"DEBUG Minimum Premium - No minimum found for {radius_category}")
        
        # Apply schedule mod to the weighted minimum
        final_minimum = total_weighted_minimum * schedule_mod
        
        print(f"DEBUG Minimum Premium - Weighted Total: {total_weighted_minimum}, After Mod: {final_minimum}")
        
        cur.close()
        conn.close()
        
        return jsonify({"minimum_premium": str(final_minimum)})
    except Exception as e:
        print(f"Minimum Premium Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- UMBI RATE ENDPOINT ---
@app.route("/rate/umbi", methods=["POST"])
def rate_umbi():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        
        print(f"DEBUG UMBI - Date: {policy_date}")
        
        rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate 
            FROM cw_umbi
            WHERE effective_date <= %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date,))
        result = cur.fetchone()
        
        if result:
            rate = result[0]
            print(f"DEBUG UMBI - Found rate: {rate}")
        else:
            print(f"DEBUG UMBI - No rate found")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate": str(rate)})
    except Exception as e:
        print(f"UMBI Rate Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- UMPD RATE ENDPOINT ---
@app.route("/rate/umpd", methods=["POST"])
def rate_umpd():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG UMPD - Date: {policy_date}, State: {state_code}")
        
        rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate 
            FROM cw_umpd
            WHERE effective_date <= %s
              AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            rate = result[0]
            print(f"DEBUG UMPD - Found rate: {rate}")
        else:
            print(f"DEBUG UMPD - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate": str(rate)})
    except Exception as e:
        print(f"UMPD Rate Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# --- UIMBI RATE ENDPOINT ---
@app.route("/rate/uimbi", methods=["POST"])
def rate_uimbi():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG UIMBI - Date: {policy_date}, State: {state_code}")
        
        rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate 
            FROM cw_uimbi
            WHERE effective_date <= %s
              AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            rate = result[0]
            print(f"DEBUG UIMBI - Found rate: {rate}")
        else:
            print(f"DEBUG UIMBI - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate": str(rate)})
    except Exception as e:
        print(f"UIMBI Rate Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- UIMPD RATE ENDPOINT ---
@app.route("/rate/uimpd", methods=["POST"])
def rate_uimpd():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG UIMPD - Date: {policy_date}, State: {state_code}")
        
        rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate 
            FROM cw_uimpd
            WHERE effective_date <= %s
              AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            rate = result[0]
            print(f"DEBUG UIMPD - Found rate: {rate}")
        else:
            print(f"DEBUG UIMPD - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate": str(rate)})
    except Exception as e:
        print(f"UIMPD Rate Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- MEDICAL PAYMENTS RATE ENDPOINT ---
@app.route("/rate/medical_payments", methods=["POST"])
def rate_medical_payments():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG Medical Payments - Date: {policy_date}, State: {state_code}")
        
        rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate 
            FROM cw_medical_payments
            WHERE effective_date <= %s
              AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            rate = result[0]
            print(f"DEBUG Medical Payments - Found rate: {rate}")
        else:
            print(f"DEBUG Medical Payments - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate": str(rate)})
    except Exception as e:
        print(f"Medical Payments Rate Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- PIP RATE ENDPOINT ---
@app.route("/rate/pip", methods=["POST"])
def rate_pip():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG PIP - Date: {policy_date}, State: {state_code}")
        
        rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate 
            FROM cw_pip
            WHERE effective_date <= %s
              AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            rate = result[0]
            print(f"DEBUG PIP - Found rate: {rate}")
        else:
            print(f"DEBUG PIP - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate": str(rate)})
    except Exception as e:
        print(f"PIP Rate Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
# --- HNOA RATE ENDPOINT ---
@app.route("/rate/hnoa", methods=["POST"])
def rate_hnoa():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG HNOA - Date: {policy_date}, State: {state_code}")
        
        rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT rate 
            FROM cw_hnoa
            WHERE effective_date <= %s
              AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            rate = result[0]
            print(f"DEBUG HNOA - Found rate: {rate}")
        else:
            print(f"DEBUG HNOA - No rate found for state {state_code}")
        
        cur.close()
        conn.close()
        
        return jsonify({"rate": str(rate)})
    except Exception as e:
        print(f"HNOA Rate Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- BIPD RATING ENDPOINT ---
@app.route("/rate/bipd", methods=["POST"])
def rate_bipd():
    try:
        data = request.json
        policy_date = data.get("effective_date")
        state_code = data.get("state_code")
        
        print(f"DEBUG BIPD - Date: {policy_date}, State: {state_code}")
        
        base_rate = Decimal('0.0')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT base_rate FROM bipd_base_rates
            WHERE effective_date <= %s AND state_code = %s
            ORDER BY effective_date DESC
            LIMIT 1;
        """
        cur.execute(sql, (policy_date, state_code))
        result = cur.fetchone()
        
        if result:
            base_rate = result[0]
            print(f"DEBUG BIPD - Found rate: {base_rate}")
        else:
            print(f"DEBUG BIPD - No rate found")
        
        cur.close()
        conn.close()
        
        return jsonify({"base_rate": str(base_rate)})
    except Exception as e:
        print(f"BIPD Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


    
@app.route("/test", methods=["GET"])
def test():
    return jsonify({"status": "working"})

if __name__ == '__main__':
    app.run(debug=True)