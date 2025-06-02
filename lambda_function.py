import json
import os
import boto3
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import traceback
import certifi
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import fitz  # PyMuPDF for PDF processing

def lambda_handler(event, context):
    """
    Main Lambda handler function
    This function is triggered by EventBridge (scheduled) or can be invoked manually
    """
    try:
        # Parse input from event
        search_terms = event.get('search_terms', os.environ.get('SEARCH_TERMS', 'default,keyword').split(','))
        date = event.get('date', None)  # None means tomorrow's date
        recipient_emails = event.get('recipient_emails', os.environ.get('EMAIL_RECIPIENTS', '').split(','))
        
        # Set date to tomorrow if not provided
        if not date:
            date = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
        
        print(f"Starting cause list search for date: {date}, terms: {search_terms}")
        
        # Initialize services
        scraper = CauseListScraper()
        emailer = EmailService()
        
        # Scrape and search PDFs
        results = scraper.search_cause_lists(date, search_terms)
        
        # Send email notification
        if results['found_matches']:
            emailer.send_success_email(recipient_emails, date, search_terms, results)
            print(f"Found {len(results['matches'])} matches - email sent successfully")
        else:
            emailer.send_no_results_email(recipient_emails, date, search_terms)
            print("No matches found - notification email sent")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Search completed successfully',
                'date': date,
                'search_terms': search_terms,
                'matches_found': len(results.get('matches', [])),
                'total_pdfs_searched': results.get('total_pdfs', 0)
            })
        }
        
    except Exception as e:
        error_message = str(e)
        stack_trace = traceback.format_exc()
        print(f"Error in lambda_handler: {error_message}")
        print(f"Stack trace: {stack_trace}")
        
        # Send error email
        try:
            emailer = EmailService()
            emailer.send_error_email(
                recipient_emails or [os.environ.get('EMAIL_RECIPIENTS', '').split(',')[0]], 
                error_message, 
                stack_trace
            )
        except:
            print("Failed to send error email")
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_message,
                'message': 'Search failed - check CloudWatch logs for details'
            })
        }


class CauseListScraper:
    def __init__(self):
        self.cl_base_url = os.environ.get('CL_BASE_URL', '')
        self.main_base_url = os.environ.get('MAIN_BASE_URL', '')
        self.form_action_url = os.environ.get('FORM_ACTION_URL', '')
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    def _create_session(self) -> requests.Session:
        """Create a session with retry logic and SSL verification"""
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('https://', adapter)
        session.verify = certifi.where()
        return session

    def search_cause_lists(self, date: str, search_terms: List[str]) -> Dict[str, Any]:
        """Main function to search cause lists for given terms"""
        print(f"Searching cause lists for date: {date}")
        
        # Get list of PDFs for the date
        pdfs = self.get_pdf_list(date)
        print(f"Found {len(pdfs)} PDFs to search")
        
        matches = []
        
        for pdf in pdfs:
            try:
                # Download and search PDF
                pdf_matches = self.search_pdf(pdf, search_terms)
                if pdf_matches:
                    matches.extend(pdf_matches)
                    print(f"Found {len(pdf_matches)} matches in {pdf['pdf_name']}")
                    
            except Exception as e:
                print(f"Error searching PDF {pdf['pdf_name']}: {str(e)}")
                continue
        
        return {
            'found_matches': len(matches) > 0,
            'matches': matches,
            'total_pdfs': len(pdfs),
            'search_date': date,
            'search_terms': search_terms
        }

    def get_pdf_list(self, date: str) -> List[Dict[str, str]]:
        """Get list of PDFs for a given date"""
        form_data = {
            "t_f_date": date,
            "urg_ord": "1",
            "action": "show_causeList",
        }

        try:
            with self._create_session() as session:
                response = session.post(self.form_action_url, data=form_data, headers=self.headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, "html.parser")
                rows = soup.select("table#tables11 tr")
                pdfs = []

                for row in rows[2:]:  # Skip header rows
                    cells = row.find_all("td")
                    if len(cells) == 3:
                        link = cells[0].find("a", href=True)
                        list_type = cells[1].text.strip()
                        main_sup = cells[2].text.strip()

                        if link:
                            pdf_url = link["onclick"].split("'")[1]
                            pdf_url = urljoin(self.cl_base_url, pdf_url)
                            pdf_name = f"{list_type} | {main_sup}"
                            pdfs.append({"pdf_name": pdf_name, "pdf_url": pdf_url})

                return pdfs
                
        except Exception as e:
            print(f"Error getting PDF list: {str(e)}")
            return []

    def search_pdf(self, pdf_info: Dict[str, str], search_terms: List[str]) -> List[Dict[str, Any]]:
        """Download and search a PDF for given terms"""
        try:
            # Download PDF
            with self._create_session() as session:
                response = session.get(pdf_info['pdf_url'], headers=self.headers)
                response.raise_for_status()
                
                # Search PDF content
                pdf_document = fitz.open("pdf", response.content)
                matches = []
                
                for page_num in range(pdf_document.page_count):
                    page = pdf_document.page(page_num)
                    page_text = page.get_text().lower()
                    
                    for term in search_terms:
                        term_lower = term.lower().strip()
                        if term_lower in page_text:
                            # Extract context around the match
                            lines = page_text.split('\n')
                            context_lines = []
                            
                            for i, line in enumerate(lines):
                                if term_lower in line:
                                    # Get context (2 lines before and after)
                                    start = max(0, i-2)
                                    end = min(len(lines), i+3)
                                    context_lines.extend(lines[start:end])
                            
                            matches.append({
                                'term': term,
                                'pdf_name': pdf_info['pdf_name'],
                                'pdf_url': pdf_info['pdf_url'],
                                'page': page_num + 1,
                                'context': '\n'.join(context_lines[:10])  # Limit context
                            })
                
                pdf_document.close()
                return matches
                
        except Exception as e:
            print(f"Error searching PDF {pdf_info['pdf_name']}: {str(e)}")
            return []


class EmailService:
    def __init__(self):
        self.sender_email = os.environ.get('SENDER_EMAIL', '')
        self.sender_password = os.environ.get('SENDER_PASSWORD', '')
        self.sender_name = os.environ.get('SENDER_NAME', 'Cause List Checker')
        self.smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))

    def send_success_email(self, recipients: List[str], date: str, search_terms: List[str], results: Dict[str, Any]):
        """Send email when matches are found"""
        subject = f"🎯 Cause List Matches Found - {date}"
        
        # Create HTML content
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; margin: 20px;">
            <h2 style="color: #2e7d32;">✅ Matches Found in Cause Lists</h2>
            <p><strong>Date:</strong> {date}</p>
            <p><strong>Search Terms:</strong> {', '.join(search_terms)}</p>
            <p><strong>Total Matches:</strong> {len(results['matches'])}</p>
            <p><strong>PDFs Searched:</strong> {results['total_pdfs']}</p>
            
            <h3>Matches Details:</h3>
        """
        
        for match in results['matches']:
            html_content += f"""
            <div style="border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px;">
                <h4 style="color: #1976d2;">📄 {match['pdf_name']}</h4>
                <p><strong>Term Found:</strong> {match['term']}</p>
                <p><strong>Page:</strong> {match['page']}</p>
                <p><strong>PDF Link:</strong> <a href="{match['pdf_url']}">View PDF</a></p>
                <div style="background-color: #f5f5f5; padding: 10px; border-radius: 3px;">
                    <strong>Context:</strong><br>
                    <pre style="white-space: pre-wrap; font-size: 12px;">{match['context'][:500]}...</pre>
                </div>
            </div>
            """
        
        html_content += f"""
            <hr>
            <p style="color: #666; font-size: 12px;">
                Generated at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S IST")}
            </p>
        </body>
        </html>
        """
        
        self._send_email(recipients, subject, html_content)

    def send_no_results_email(self, recipients: List[str], date: str, search_terms: List[str]):
        """Send email when no matches are found"""
        subject = f"📋 No Matches Found - {date}"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; margin: 20px;">
            <h2 style="color: #ff9800;">📋 No Matches Found</h2>
            <p><strong>Date:</strong> {date}</p>
            <p><strong>Search Terms:</strong> {', '.join(search_terms)}</p>
            <p>No matches were found for your search terms in today's cause lists.</p>
            <p style="color: #666; font-size: 12px;">
                Generated at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S IST")}
            </p>
        </body>
        </html>
        """
        
        self._send_email(recipients, subject, html_content)

    def send_error_email(self, recipients: List[str], error_message: str, stack_trace: str):
        """Send email when an error occurs"""
        subject = "❌ Cause List Checker Error"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; margin: 20px;">
            <h2 style="color: #d32f2f;">❌ Error in Cause List Checker</h2>
            <p>An error occurred while processing the cause list search:</p>
            
            <div style="background-color: #ffebee; padding: 15px; border-radius: 5px; margin: 10px 0;">
                <h4>Error Message:</h4>
                <pre style="color: #d32f2f;">{error_message}</pre>
            </div>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 10px 0;">
                <h4>Stack Trace:</h4>
                <pre style="font-size: 11px; overflow-x: auto;">{stack_trace}</pre>
            </div>
            
            <p style="color: #666; font-size: 12px;">
                Generated at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S IST")}
            </p>
        </body>
        </html>
        """
        
        self._send_email(recipients, subject, html_content)

    def _send_email(self, recipients: List[str], subject: str, html_content: str):
        """Send email using SMTP"""
        try:
            msg = MIMEMultipart()
            msg["From"] = f"{self.sender_name} <{self.sender_email}>"
            msg["To"] = ", ".join(recipients)
            msg["Subject"] = subject
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, recipients, msg.as_string())
                
            print(f"Email sent successfully to {recipients}")
            
        except Exception as e:
            print(f"Error sending email: {str(e)}")
            raise e 