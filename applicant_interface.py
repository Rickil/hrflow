import streamlit as st
import os
import uuid
from pydparser import ResumeParser
from sentiment_analysis import sentiment_analysis_model
from scoring import calculate_matching_score
import sqlite3
import json

def applicant_interface():
    st.title("Job Application Portal")

    # Connect to the database
    conn = sqlite3.connect('data/database.db')
    c = conn.cursor()

    # Fetch available job offers
    c.execute('''SELECT job_id, title FROM job_offers''')
    job_offers = c.fetchall()

    if job_offers:
        # Let applicant select a job offer
        job_options = {job_id: title for job_id, title in job_offers}
        selected_job_id = st.selectbox("Select a job offer to apply for", options=list(job_options.keys()), format_func=lambda x: job_options[x])

        if selected_job_id:
            # Retrieve the job description skills for the selected job offer
            c.execute('''SELECT required_skills FROM job_offers WHERE job_id = ?''', (selected_job_id,))
            job_offer = c.fetchone()
            job_description_skills = json.loads(job_offer[0])

            # Resume upload
            uploaded_file = st.file_uploader("Upload your resume (PDF)", type="pdf")

            if uploaded_file is not None:
                # Generate a unique ID for the applicant
                applicant_id = str(uuid.uuid4())
                resume_path = f"data/resumes/{applicant_id}.pdf"
                os.makedirs(os.path.dirname(resume_path), exist_ok=True)

                # Save the uploaded resume
                with open(resume_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                # Extract text and skills from the resume
                extracted_skills = ResumeParser(resume_path).get_extracted_data()['skills']

                # Compare skills to find missing ones
                missing_skills = list(set(job_description_skills) - set(extracted_skills))

                # Store missing skills in session state
                if 'missing_skills' not in st.session_state:
                    st.session_state['missing_skills'] = missing_skills

                if missing_skills:
                    st.write("Based on your resume, the following skills are missing:")

                    # Allow the applicant to select skills to provide answers for
                    selected_skills = st.multiselect(
                        "Select the skills you'd like to provide more information on:",
                        options=st.session_state['missing_skills'],
                        default=st.session_state.get('selected_skills', []),
                        key='selected_skills'
                    )

                    # Collect answers for the selected skills
                    st.write("Please provide details for the selected skills:")
                    for skill in selected_skills:
                        answer_key = f"answer_{skill}"
                        st.text_area(
                            f"Describe your experience with {skill}:",
                            key=answer_key
                        )

                    if st.button("Submit Application"):
                        # Gather answers from session state
                        answers = {}
                        for skill in st.session_state['missing_skills']:
                            answer_key = f"answer_{skill}"
                            # For skills not selected, the answer will be an empty string
                            answers[skill] = st.session_state.get(answer_key, "")
                        
                        # remove empty answers
                        answers = {k: v for k, v in answers.items() if v}

                        # Validate answers using sentiment analysis
                        validated_answers = {}
                        for skill, answer in answers.items():
                            validation = sentiment_analysis_model(answer)
                            validated_answers[skill] = validation

                        # Calculate the matching score
                        matching_score = calculate_matching_score(extracted_skills, validated_answers, job_description_skills)

                        # Save applicant data to the database
                        applicant_data = {
                            'applicant_id': applicant_id,
                            'job_id': selected_job_id,
                            'extracted_skills': extracted_skills,
                            'answers': answers,
                            'validated_answers': validated_answers,
                            'matching_score': matching_score
                        }

                        c.execute('''INSERT INTO applicants (applicant_id, job_id, data) VALUES (?, ?, ?)''',
                                  (applicant_id, selected_job_id, json.dumps(applicant_data)))
                        conn.commit()

                        # Clear session state
                        for key in list(st.session_state.keys()):
                            if key.startswith('answer_') or key in ['missing_skills', 'selected_skills']:
                                del st.session_state[key]

                        st.success("Your application has been submitted!")
                else:
                    st.write("Great! Your resume matches all the required skills.")
                    if st.button("Submit Application"):
                        # Calculate the matching score
                        matching_score = calculate_matching_score(extracted_skills, {}, job_description_skills)

                        # Save applicant data to the database
                        applicant_data = {
                            'applicant_id': applicant_id,
                            'job_id': selected_job_id,
                            'extracted_skills': extracted_skills,
                            'answers': {},
                            'validated_answers': {},
                            'matching_score': matching_score
                        }

                        c.execute('''INSERT INTO applicants (applicant_id, job_id, data) VALUES (?, ?, ?)''',
                                  (applicant_id, selected_job_id, json.dumps(applicant_data)))
                        conn.commit()

                        st.success("Your application has been submitted!")
            else:
                st.info("Please upload your resume to proceed.")
        else:
            st.warning("No job offer selected.")
    else:
        st.write("No job offers available at the moment.")

    conn.close()