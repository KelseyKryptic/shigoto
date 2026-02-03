import streamlit as st
import PyPDF2
import docx
import requests
from googlesearch import search
import time
import json

# --- Configuration ---
st.set_page_config(
    page_title="Direct Job Search Bot",
    page_icon="🤖",
    layout="wide"
)

# --- Helper Functions ---

def extract_text_from_pdf(file):
    """Extracts text from uploaded PDF file."""
    try:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return None

def extract_text_from_docx(file):
    """Extracts text from uploaded DOCX file."""
    try:
        doc = docx.Document(file)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    except Exception as e:
        st.error(f"Error reading DOCX: {e}")
        return None

def analyze_resume_direct_api(text, api_key):
    """
    Directly hits the Gemini REST API, bypassing Python SDK errors.
    """
    # Using the v1beta endpoint
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    prompt = f"""
    You are an expert career coach. Analyze the following resume text.
    Identify the top 3-5 relevant job titles this candidate is qualified for.
    Also, identify their top 5 core technical skills.
    
    Return the response strictly in this format:
    TITLES: Title 1, Title 2, Title 3
    SKILLS: Skill 1, Skill 2, Skill 3
    
    Resume Text:
    {text[:4000]}
    """
    
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code != 200:
            st.error(f"API Error ({response.status_code}): {response.text}")
            return None
            
        result = response.json()
        
        # Robust parsing of the JSON response
        try:
            return result['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError, TypeError):
            # Fallback if structure is slightly different
            st.error(f"Unexpected JSON structure: {result}")
            return None
            
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None

def is_valid_link(url):
    """Checks if a link is active and not a job board."""
    try:
        excluded_domains = [
            "linkedin.com", "indeed.com", "glassdoor.com", 
            "ziprecruiter.com", "monster.com", "simplyhired.com"
        ]
        
        if any(domain in url for domain in excluded_domains):
            return False

        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.head(url, headers=headers, timeout=3, allow_redirects=True)
        
        return response.status_code == 200
    except:
        return False

def generate_search_queries(titles, remote_only):
    """Generates Google Dorks."""
    queries = []
    base_query = 'site:lever.co OR site:greenhouse.io OR site:myworkdayjobs.com OR site:smartrecruiters.com'
    
    for title in titles:
        location_param = '"remote"' if remote_only else ""
        query = f'{base_query} "{title}" {location_param} -intitle:archive -intitle:closed'
        queries.append(query)
    
    return queries

# --- Main Application Layout ---

st.title("🤖 Direct Job Search Bot")

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Secrets management
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("API Key loaded from Secrets")
    else:
        api_key = st.text_input("Enter Gemini API Key", type="password")

    remote_only = st.checkbox("Remote Only", value=True)

# --- Main Logic ---

uploaded_file = st.file_uploader("Upload your Resume (PDF or DOCX)", type=["pdf", "docx"])

if uploaded_file and api_key:
    with st.spinner("Reading resume..."):
        if uploaded_file.name.endswith(".pdf"):
            resume_text = extract_text_from_pdf(uploaded_file)
        elif uploaded_file.name.endswith(".docx"):
            resume_text = extract_text_from_docx(uploaded_file)
            
    if resume_text:
        if "job_titles" not in st.session_state:
            with st.spinner("Analyzing profile..."):
                analysis = analyze_resume_direct_api(resume_text, api_key)
                
                if analysis:
                    lines = analysis.split('\n')
                    titles_line = next((line for line in lines if "TITLES:" in line), "TITLES: Generalist")
                    skills_line = next((line for line in lines if "SKILLS:" in line), "SKILLS: Python")
                    
                    st.session_state['job_titles'] = [t.strip() for t in titles_line.replace("TITLES:", "").split(",")]
                    st.session_state['skills'] = [s.strip() for s in skills_line.replace("SKILLS:", "").split(",")]
        
        if 'job_titles' in st.session_state:
            st.success("Analysis Complete")
            st.write(f"**Roles:** {', '.join(st.session_state['job_titles'])}")
            st.write(f"**Skills:** {', '.join(st.session_state['skills'])}")

            if st.button("🚀 Find Direct Links"):
                queries = generate_search_queries(st.session_state['job_titles'], remote_only)
                progress = st.progress(0)
                
                for i, query in enumerate(queries):
                    try:
                        results = search(query, num=5, stop=5, pause=2
