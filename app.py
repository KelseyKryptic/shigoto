import streamlit as st
import google.generativeai as genai
import PyPDF2
import docx
import requests
from googlesearch import search
import time
import random

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

def analyze_resume_with_gemini(text, api_key):
    """Uses Gemini Pro to extract skills and job titles."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
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
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"Gemini API Error: {e}")
        return None

def is_valid_link(url):
    """Checks if a link is active (Status 200) and filters out common junk."""
    try:
        # distinct filtering logic
        excluded_domains = [
            "linkedin.com", "indeed.com", "glassdoor.com", 
            "ziprecruiter.com", "monster.com", "simplyhired.com"
        ]
        
        # 1. Domain Check
        if any(domain in url for domain in excluded_domains):
            return False

        # 2. ATS / Direct Company Check (Heuristic)
        # We prioritize these, but we don't strictly exclude others to allow for direct company sites
        # common_ats = ["workday", "lever", "greenhouse", "icims", "jobvite", "smartrecruiters"]
        
        # 3. Dead Link Check (HEAD request is faster than GET)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.head(url, headers=headers, timeout=3, allow_redirects=True)
        
        if response.status_code == 200:
            return True
        return False
    except:
        return False

def generate_search_queries(titles, remote_only):
    """Generates Google Dorks based on extracted titles."""
    queries = []
    base_query = 'site:lever.co OR site:greenhouse.io OR site:myworkdayjobs.com OR site:smartrecruiters.com'
    
    for title in titles:
        # Constructing a Dork that looks for the title inside common ATS domains
        # This is often more effective than "site:*.com" which returns too much noise
        location_param = '"remote"' if remote_only else ""
        query = f'{base_query} "{title}" {location_param} -intitle:archive -intitle:closed'
        queries.append(query)
    
    return queries

# --- Main Application Layout ---

st.title("🤖 Direct Job Search Bot")
st.markdown("""
**Find hidden jobs directly on company career pages.** *This bot parses your resume, generates targeted Google Dorks, and finds direct application links posted recently.*
""")

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Enter Gemini API Key", type="password", help="Get one from Google AI Studio")
    st.markdown("---")
    st.subheader("Search Preferences")
    remote_only = st.checkbox("Remote Only", value=True)
    exclude_boards = st.checkbox("Exclude Job Boards", value=True, disabled=True, help="Always active to ensure direct links.")
    
    st.markdown("---")
    st.info("💡 **Note:** This tool uses Google Search. Frequent use may verify you are not a robot.")

# --- Main Interface ---

uploaded_file = st.file_uploader("Upload your Resume (PDF or DOCX)", type=["pdf", "docx"])

if uploaded_file and api_key:
    # 1. Parse Resume
    with st.spinner("Reading resume..."):
        if uploaded_file.name.endswith(".pdf"):
            resume_text = extract_text_from_pdf(uploaded_file)
        elif uploaded_file.name.endswith(".docx"):
            resume_text = extract_text_from_docx(uploaded_file)
            
    if resume_text:
        # 2. Analyze with AI
        if "job_titles" not in st.session_state:
            with st.spinner("Analyzing profile with Gemini..."):
                analysis = analyze_resume_with_gemini(resume_text, api_key)
                if analysis:
                    # Simple parsing of the AI response
                    lines = analysis.split('\n')
                    titles_line = next((line for line in lines if "TITLES:" in line), "TITLES: Generalist")
                    skills_line = next((line for line in lines if "SKILLS:" in line), "SKILLS: Python")
                    
                    extracted_titles = [t.strip() for t in titles_line.replace("TITLES:", "").split(",")]
                    extracted_skills = [s.strip() for s in skills_line.replace("SKILLS:", "").split(",")]
                    
                    st.session_state['job_titles'] = extracted_titles
                    st.session_state['skills'] = extracted_skills
        
        # Display AI Findings
        if 'job_titles' in st.session_state:
            st.success("Resume Analyzed!")
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Target Roles Identified:**")
                for t in st.session_state['job_titles']:
                    st.write(f"- {t}")
            with col2:
                st.write("**Core Skills:**")
                st.write(", ".join(st.session_state['skills']))

            # 3. Search Button
            if st.button("🚀 Find Direct Job Links"):
                
                results_container = st.empty()
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Generate Queries
                queries = generate_search_queries(st.session_state['job_titles'], remote_only)
                
                all_results = []
                total_queries = len(queries)
                
                for i, query in enumerate(queries):
                    status_text.text(f"Scouring the web for: {st.session_state['job_titles'][i]}...")
                    
                    try:
                        # Perform Google Search
                        # tbs="qdr:d" filters for results indexed in the last 24 hours (past day)
                        # pause=2.0 helps prevent hitting rate limits too fast
                        search_results = search(query, num=10, stop=10, pause=2.0, extra_params={'tbs': 'qdr:d'})
                        
                        for url in search_results:
                            # Strict Filtering & Dead Link Check
                            if is_valid_link(url):
                                all_results.append({
                                    "Role": st.session_state['job_titles'][i],
                                    "Source": url.split("/")[2], # Extract domain
                                    "URL": url
                                })
                                
                    except Exception as e:
                        st.warning(f"Search rate limit hit for query {i+1}. Try again later.")
                        break
                    
                    # Update Progress
                    progress_bar.progress((i + 1) / total_queries)
                    time.sleep(1) # Politeness delay

                progress_bar.progress(100)
                status_text.text("Search Complete!")
                
                # 4. Results Gallery
                if all_results:
                    st.subheader(f"Found {len(all_results)} Active Direct Links (Last 24h)")
                    
                    for job in all_results:
                        with st.container():
                            c1, c2, c3 = st.columns([3, 2, 2])
                            with c1:
                                st.markdown(f"**{job['Role']}**")
                            with c2:
                                st.write(f"🏢 {job['Source']}")
                            with c3:
                                st.link_button("Apply Directly 🔗", job['URL'])
                            st.divider()
                else:
                    st.warning("No direct links found matching strict criteria. Try broadening your resume keywords.")

elif not api_key:

    st.warning("Please enter your Gemini API Key in the sidebar to proceed.")
