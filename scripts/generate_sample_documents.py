"""Generates comprehensive, realistic financial PDFs and indexes them into the vector/keyword store.

Creates authentic multi-page legal contracts with full preambles, recitals, definitions, 
detailed schedules, covenants, sub-limits, fee structures, and exclusions.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ingestion.pdf_parser import create_sample_pdf, compute_content_hash, extract_text_from_pdf
from app.ingestion.chunker import chunk_document
from app.ingestion.embedder import get_text_embedding
from app.db.connection import SessionLocal
from app.db.models import Document, Chunk

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "documents")

SAMPLE_DOCS = [
    {
        "filename": "home_loan_agreement.pdf",
        "doc_type": "loan",
        "title": "HOME LOAN AGREEMENT",
        "pages": [
            {
                "section": "ARTICLE 1: SANCTION TERMS, PRINCIPAL, AND REPAYMENT",
                "text": (
                    "THIS HOUSING LOAN AGREEMENT is executed between HDFC Housing Finance Limited (hereinafter referred to "
                    "as the 'Lender') and Aarav Sharma, residing at Flat 402, Green Glen Layout, Bellandur, Bangalore "
                    "(hereinafter referred to as the 'Borrower').\n\n"
                    "1.1 Loan Facility: The Lender agrees to lend and the Borrower agrees to borrow a housing term loan "
                    "facility of a principal sum of ₹75,00,000 (Rupees Seventy-Five Lakhs Only) for a total tenure of 240 months "
                    "(20 calendar years).\n\n"
                    "1.2 Interest Rate Structure: The loan carries a floating interest rate of 8.50% per annum, calculated on a "
                    "daily reducing balance. The rate is pegged to the External Benchmark Lending Rate (EBLR) of the Reserve Bank "
                    "of India (Repo Rate of 6.50%) plus an ongoing operational spread of 2.00% per annum. Any revision in the EBLR "
                    "shall be automatically reset on the first day of the following quarter.\n\n"
                    "1.3 Equated Monthly Installment (EMI): The Borrower shall repay the loan in 240 consecutive monthly "
                    "installments of ₹65,066 (Rupees Sixty-Five Thousand Sixty-Six Only). The first installment shall commence "
                    "on the 5th of the month following complete disbursement, payable via National Automated Clearing House (NACH) "
                    "mandate or Electronic Clearing Service (ECS)."
                )
            },
            {
                "section": "ARTICLE 2: DISBURSEMENT SCHEDULE AND MORTGAGE SECURITY",
                "text": (
                    "2.1 Stage-Wise Construction Disbursements: The loan shall be disbursed directly to the developer/vendor in "
                    "stages corresponding strictly to verified construction milestones: (a) 20% on foundation completion, "
                    "(b) 40% on structural slab completion, (c) 30% on interior plastering and plumbing, and (d) 10% on issuance "
                    "of the municipal occupancy certificate. Prior to each stage release, an inspection report from a certified "
                    "structural chartered engineer must be submitted.\n\n"
                    "2.2 Creation of Equitable Mortgage: As primary security for the repayment of the loan and interest, the Borrower "
                    "creates an exclusive first charge by way of an equitable mortgage on the immovable property located at Flat 402, "
                    "Green Glen Layout, Bellandur, Bangalore - 560103. The Borrower deposits original title deeds, sanctioned building "
                    "plans, encumbrance certificates for the preceding 30 years, and khata certificates with the Lender.\n\n"
                    "2.3 Maintenance of Property Insurance: The Borrower shall keep the mortgaged property comprehensively insured "
                    "against fire, flood, earthquake, and allied perils for an amount not less than the full replacement cost (₹85,00,000), "
                    "duly assigning the policy in favor of the Lender."
                )
            },
            {
                "section": "ARTICLE 3: EVENTS OF DEFAULT AND STATUTORY RECOVERY",
                "text": (
                    "3.1 Events of Default: The occurrence of any of the following shall constitute an immediate Event of Default:\n"
                    "(a) Non-payment of three consecutive Equated Monthly Installments (EMIs) on their respective due dates;\n"
                    "(b) Failure to furnish property insurance renewal certificates or municipal property tax receipts;\n"
                    "(c) Any material misrepresentation in financial statements, employment verification, or title documents;\n"
                    "(d) Initiation of any insolvency, bankruptcy, or debt recovery proceedings against the Borrower.\n\n"
                    "3.2 Acceleration and Enforcement: Upon the occurrence of an Event of Default, the entire outstanding principal, "
                    "accrued interest, penal charges, and legal expenses shall become immediately due and payable. The Lender shall "
                    "be entitled to invoke the provisions of the Securitisation and Reconstruction of Financial Assets and Enforcement "
                    "of Security Interest Act, 2002 (SARFAESI Act 2002).\n\n"
                    "3.3 Statutory Demand Notice: The Lender shall issue a statutory 60-day demand notice under Section 13(2) of "
                    "the SARFAESI Act requiring discharge of liabilities in full. Failure to comply shall entitle the Lender to take "
                    "possession of the secured asset, sell the property through public auction, or appoint a manager over the property."
                )
            },
            {
                "section": "ARTICLE 4: PREPAYMENT, PART-PAYMENT, AND FORECLOSURE CHARGES",
                "text": (
                    "4.1 Lock-in Period: The Borrower is subject to a mandatory lock-in period of 12 months from the date of final "
                    "disbursement, during which no complete loan foreclosure is permitted.\n\n"
                    "4.2 Prepayment Penalties on Individual Floating Rate Loans: In strict adherence to Reserve Bank of India (RBI) "
                    "regulatory guidelines (Circular DBOD.Dir.BC.107/13.03.00/2011-12), no prepayment penalty (0% fee) shall be levied "
                    "on individual borrowers prepaying floating rate home loans, irrespective of whether the prepayment is partial or full, "
                    "and regardless of the source of funds.\n\n"
                    "4.3 Fixed Rate or Commercial Borrowing Prepayment Charges: For fixed-rate home loan contracts or non-individual "
                    "(corporate/commercial) borrowers, a prepayment penalty is 2% of outstanding principal plus applicable Goods and "
                    "Services Tax (GST). Any partial prepayment must be a minimum of ₹50,000 and can be exercised at most four times "
                    "within a single financial year.\n\n"
                    "4.4 Intimation Procedure: To initiate foreclosure, the Borrower must submit written intimation 15 working days "
                    "in advance, accompanied by original identity proofs and account statements."
                )
            },
            {
                "section": "ARTICLE 5: TAX PROVISIONS, STATUTORY DISCLOSURES, AND NOTICES",
                "text": (
                    "5.1 Income Tax Deductions: Borrowers are eligible for income tax benefits under the Income Tax Act, 1961:\n"
                    "(a) Deduction under Section 80C on account of principal repayment up to ₹1,50,000 per financial year, subject to "
                    "the aggregate limit of Section 80C;\n"
                    "(b) Deduction under Section 24(b) on account of interest payments up to ₹2,00,000 per financial year for a "
                    "self-occupied property (or full interest for let-out properties);\n"
                    "(c) Additional deduction under Section 80EEA up to ₹1,50,000 for affordable housing loan sanctions satisfying "
                    "stamp duty valuation caps.\n\n"
                    "5.2 Provisional and Final Tax Certificates: The Lender shall issue a provisional tax interest certificate in "
                    "April of each financial year estimating scheduled interest and principal, and a final audited certificate in May "
                    "reflecting actual payments realized.\n\n"
                    "5.3 Jurisdiction and Dispute Resolution: Any legal dispute arising under this Agreement shall be subject to the "
                    "exclusive jurisdiction of competent civil courts located in Bangalore, Karnataka."
                )
            }
        ]
    },
    {
        "filename": "car_loan_agreement.pdf",
        "doc_type": "loan",
        "title": "AUTO VEHICLE LOAN AGREEMENT",
        "pages": [
            {
                "section": "ARTICLE 1: VEHICLE HYPOTHECATION FACILITY AND SANCTION",
                "text": (
                    "THIS AUTO LOAN AGREEMENT is made between ICICI Bank Limited (the 'Financier') and Aarav Sharma (the 'Borrower').\n\n"
                    "1.1 Facility Amount: The Financier sanctions a vehicle loan facility of ₹12,00,000 (Rupees Twelve Lakhs Only) "
                    "for the purchase of a new passenger vehicle: Hyundai Creta SX(O) 1.5L Turbo Petrol, Engine No: G4LD-839210, "
                    "Chassis No: MALC-948201.\n\n"
                    "1.2 Fixed Interest Rate: The loan carries a fixed interest rate of 8.75% per annum for the entire contracted "
                    "tenure of 60 months (5 years). The interest rate shall remain unaltered throughout the loan term, irrespective of "
                    "macroeconomic benchmark fluctuations.\n\n"
                    "1.3 Security: The vehicle shall remain exclusively hypothecated in favor of the Financier until issuance of an "
                    "official No Objection Certificate (NOC) and Form 35 submission to the Regional Transport Office (RTO)."
                )
            },
            {
                "section": "ARTICLE 2: EMI SCHEDULE, LATE FEES, AND PENAL INTEREST",
                "text": (
                    "2.1 Monthly Installment: The Borrower covenants to pay a fixed Equated Monthly Installment (EMI) of ₹24,765 "
                    "(Rupees Twenty-Four Thousand Seven Hundred Sixty-Five Only) due on or before the 10th of every calendar month.\n\n"
                    "2.2 Late Payment Penalty and Bounce Charges: In the event of NACH/ECS mandate dishonor, an electronic bounce fee "
                    "of ₹500 plus applicable taxes shall be debited immediately. Furthermore, a late payment penalty fee of ₹500 plus "
                    "2% monthly penal interest (equivalent to 24% per annum) shall be levied on all overdue unpaid installment balances "
                    "calculated from the due date until realization.\n\n"
                    "2.3 Repossession Clause: Default exceeding 60 consecutive days entitles the Financier's authorized recovery agents "
                    "to take physical possession of the hypothecated vehicle after serving a 7-day cure notice."
                )
            },
            {
                "section": "ARTICLE 3: FORECLOSURE GUIDELINES AND PART-PREPAYMENT",
                "text": (
                    "3.1 Foreclosure Eligibility: Foreclosure of the vehicle loan facility is permitted only after the completion of "
                    "6 months from the date of initial disbursement.\n\n"
                    "3.2 Foreclosure Fee: A foreclosure fee of 3% on the outstanding principal balance at the time of pre-closure plus "
                    "applicable GST shall be charged. If foreclosure is initiated within 12 to 24 months, the fee is 3%; after 24 months, "
                    "the fee reduces to 2%.\n\n"
                    "3.3 Partial Prepayment Restrictions: No partial prepayment is allowed within the first 6 months. Thereafter, partial "
                    "prepayment is permitted up to a maximum of twice in any financial year, provided each partial prepayment is equal to "
                    "or greater than the sum of 3 regular EMIs (minimum ₹74,295)."
                )
            }
        ]
    },
    {
        "filename": "health_insurance_policy.pdf",
        "doc_type": "insurance",
        "title": "COMPREHENSIVE HEALTH INSURANCE POLICY",
        "pages": [
            {
                "section": "SECTION 1: POLICY SCHEDULE AND INPATIENT BENEFITS",
                "text": (
                    "STAR HEALTH AND ALLIED INSURANCE COMPANY LIMITED\n"
                    "Policy Certificate No: SH-COMP-8392104-2026\n"
                    "Primary Policyholder: Aarav Sharma | Insured Age: 34 | Nominee: Priya Sharma\n\n"
                    "1.1 Sum Insured: The basic sum insured under this policy is ₹10,00,000 (Rupees Ten Lakhs Only) per policy year, "
                    "applicable on an individual floater basis.\n\n"
                    "1.2 Inpatient Hospitalization: Coverage covers hospitalization exceeding 24 hours for medically necessary treatment: "
                    "room charges, nursing expenses, surgeon fees, anesthetist fees, oxygen, operation theatre charges, surgical appliances, "
                    "and medicines prescribed during hospitalization.\n\n"
                    "1.3 Pre and Post Hospitalization: Medical expenses incurred up to 60 days pre-hospitalization and up to 90 days "
                    "post-hospitalization are covered provided they relate directly to the recognized inpatient admission."
                )
            },
            {
                "section": "SECTION 2: INITIAL WAITING PERIODS AND PRE-EXISTING DISEASES",
                "text": (
                    "2.1 Initial Waiting Period: A mandatory initial waiting period of 30 days from the inception date applies to all "
                    "illnesses and medical conditions. No claims are payable for illnesses diagnosed during this period, except those "
                    "arising directly from accidental bodily injuries sustained after the policy commencement date.\n\n"
                    "2.2 Pre-Existing Conditions: A strict waiting period of 24 months applies to pre-existing ailments, defined as any "
                    "condition, ailment, injury, or disease diagnosed by a physician within 48 months prior to policy issuance. This includes "
                    "Type 2 diabetes mellitus, systemic hypertension, chronic kidney disease, and cardiovascular conditions.\n\n"
                    "2.3 Specific Ailment Exclusions (24 Months): Cataract surgery, benign prostatic hypertrophy, hernia repair, hydrocele, "
                    "piles, fistula, gallstones, and joint replacement surgeries carry an unconditional 24-month waiting period."
                )
            },
            {
                "section": "SECTION 3: ROOM RENT CAPS, ICU LIMITS, AND PROPORTIONATE DEDUCTION",
                "text": (
                    "3.1 Normal Room Rent Limit: Hospitalization room rent is capped at 1% of the basic sum insured per day "
                    "(₹10,000 per day for a ₹10,00,000 policy). This limit includes all nursing, boarding, and room service charges.\n\n"
                    "3.2 Intensive Care Unit (ICU) Limit: Intensive Care Unit (ICU) and Intensive Coronary Care Unit (ICCU) charges are "
                    "capped at 2% of the basic sum insured per day (₹20,000 per day).\n\n"
                    "3.3 Proportionate Deduction Clause: In the event the insured chooses a hospital room category with daily charges "
                    "exceeding the 1% cap (e.g. ₹15,000/day suite), the insurer shall apply proportionate deduction. All associated "
                    "variable medical expenses—including doctors' consultation fees, operating surgeon fees, and diagnostic testing—shall "
                    "be reimbursed only in the proportion that the allowed room rent limit bears to the actual room tariff charged."
                )
            },
            {
                "section": "SECTION 4: CUMULATIVE BONUS AND AUTOMATIC SUM INSURED RESTORATION",
                "text": (
                    "4.1 Cumulative No-Claim Bonus (NCB): A cumulative bonus of 10% on basic sum insured for each claim-free year is "
                    "credited to the policy, up to a maximum cumulative bonus cap of 100% of the initial sum insured (₹10,00,000 bonus, "
                    "yielding a maximum effective cover of ₹20,00,000). The cumulative bonus is reduced by 10% in any policy year where "
                    "a claim is admitted, but basic sum insured remains untouched.\n\n"
                    "4.2 Automatic 100% Restoration: If the basic sum insured and accrued cumulative bonus are completely exhausted due "
                    "to claims paid during the policy year, automatic restoration of 100% basic sum insured is triggered once per policy year "
                    "at zero additional premium. Restored funds are accessible for subsequent distinct hospitalizations."
                )
            },
            {
                "section": "SECTION 5: MATERNITY BENEFIT, CRITICAL ILLNESS, AND GENERAL EXCLUSIONS",
                "text": (
                    "5.1 Maternity Benefit: Maternity expenses are covered up to ₹50,000 for normal and cesarean deliveries, including "
                    "newborn baby care from day one up to 90 days. This benefit is subject to a strict waiting period of 36 months of "
                    "continuous coverage under this policy.\n\n"
                    "5.2 Critical Illness Cover: The policy includes a supplemental critical illness lump sum benefit covering 32 specified "
                    "life-threatening illnesses (such as cancer of specified severity, first heart attack, stroke, open chest CABG, and "
                    "major organ transplant) with a 30-day post-diagnosis survival clause.\n\n"
                    "5.3 General Exclusions: The insurer will not reimburse expenses incurred for: cosmetic or aesthetic surgeries, "
                    "weight-loss procedures, gender reassignment, experimental or unproven therapies, self-inflicted injuries or suicide "
                    "attempts, and routine dental procedures unless mandated by accidental jaw injury."
                )
            }
        ]
    },
    {
        "filename": "term_life_insurance.pdf",
        "doc_type": "insurance",
        "title": "TERM LIFE ASSURANCE CONTRACT",
        "pages": [
            {
                "section": "PART A: POLICY SPECIFICATIONS AND DEATH BENEFIT",
                "text": (
                    "HDFC LIFE INSURANCE COMPANY LIMITED - CLICK 2 PROTECT LIFE\n"
                    "Policyholder: Aarav Sharma | Date of Inception: 15-Jan-2022 | Life Assured: Aarav Sharma\n\n"
                    "1.1 Death Benefit: The total death benefit sum assured is ₹1,50,00,000 (Rupees One Crore Fifty Lakhs Only), "
                    "payable to the designated nominee (Priya Sharma) in the event of death of the Life Assured during the policy term.\n\n"
                    "1.2 Annual Premium: The regular annual premium is ₹18,450 (Rupees Eighteen Thousand Four Hundred Fifty Only), "
                    "payable annually until the Life Assured reaches the age of 65 years.\n\n"
                    "1.3 Grace Period: A grace period of 30 calendar days is allowed for annual premium payments. The risk cover remains "
                    "fully in force during the grace period."
                )
            },
            {
                "section": "PART B: RIDERS, CRITICAL ILLNESS, AND SUICIDE EXCLUSIONS",
                "text": (
                    "2.1 Suicide Exclusion Clause: In the event of suicide within 12 months from the policy inception date, the policy "
                    "shall be rendered void, and the insurer will refund 80% of all premiums paid without interest, paying no sum assured.\n\n"
                    "2.2 Accidental Death Benefit Rider: An additional accidental death benefit rider of ₹50,00,000 is attached to the policy, "
                    "payable over and above the primary sum assured if death occurs as a direct consequence of an accident.\n\n"
                    "2.3 Critical Illness Waiver of Premium Rider: If the Life Assured is diagnosed with any of the 19 pre-defined critical "
                    "illnesses, all future premium payments under the contract are waived while the full risk cover continues undisturbed."
                )
            }
        ]
    },
    {
        "filename": "bank_statement_hdfc.pdf",
        "doc_type": "statement",
        "title": "HDFC BANK ACCOUNT STATEMENT & SCHEDULE OF CHARGES",
        "pages": [
            {
                "section": "SCHEDULE 1: ACCOUNT DETAILS AND MINIMUM BALANCE RULES",
                "text": (
                    "HDFC BANK LIMITED - RETAIL BANKING DIVISION\n"
                    "Account Name: Aarav Sharma | Savings Account No: 501004928192 | Branch: Bellandur, Bangalore\n"
                    "IFSC Code: HDFC0001042 | Customer ID: 94820194\n\n"
                    "1.1 Average Monthly Balance (AMB) Requirement: An average monthly balance of ₹10,000 is required for regular "
                    "savings accounts in metro and urban branches. The AMB is computed as the sum of daily end-of-day balances divided "
                    "by the total number of days in the calendar month.\n\n"
                    "1.2 Non-Maintenance Penalty: If the customer fails to maintain the required AMB, a non-maintenance charge of ₹450 "
                    "per quarter plus applicable Goods and Services Tax (GST) shall be automatically debited from the account."
                )
            },
            {
                "section": "SCHEDULE 2: DEBIT CARD FEES, ATM CHARGES, AND FOREX MARKUP",
                "text": (
                    "2.1 Debit Card Annual Maintenance Fee: The debit card annual maintenance fee is ₹499 plus 18% GST (total ₹589), "
                    "billed annually in the anniversary month of card issuance.\n\n"
                    "2.2 Automated Teller Machine (ATM) Allowances: Account holders receive 5 free ATM withdrawals per calendar month "
                    "at HDFC Bank ATMs, and 3 free ATM transactions per month at other non-HDFC domestic bank ATMs. Any subsequent domestic "
                    "ATM cash withdrawal beyond the allowance incurs a fee of ₹21 plus taxes per transaction.\n\n"
                    "2.3 International Cash Withdrawal and POS Markup: For transactions abroad, an international cash withdrawal fee of ₹125 "
                    "plus a foreign currency conversion markup of 3.5% of the transaction value shall be levied on all international debits."
                )
            }
        ]
    },
    {
        "filename": "bank_statement_icici.pdf",
        "doc_type": "statement",
        "title": "ICICI BANK CREDIT CARD STATEMENT & TARIFF",
        "pages": [
            {
                "section": "STATEMENT 1: CARD ACCOUNT LIMITS AND REVOLVING APR",
                "text": (
                    "ICICI BANK CREDIT CARDS DIVISION - MONTHLY CARD STATEMENT\n"
                    "Cardholder: Aarav Sharma | Card Variant: Coral Visa Card ending in 4091\n"
                    "Billing Cycle: 15th to 14th | Payment Due Date: 05th of every month\n\n"
                    "1.1 Credit and Cash Limits: Total credit limit is ₹3,00,000 (Rupees Three Lakhs Only). Available cash advance limit "
                    "is ₹60,000 (20% of total credit limit).\n\n"
                    "1.2 Finance Charges and APR: If the total amount due is not paid in full by the due date, finance charges of 3.5% per "
                    "month (equivalent to an Annual Percentage Rate of 42% APR) are charged on revolving credit balances, calculated daily "
                    "from the date of transaction until full settlement."
                )
            },
            {
                "section": "STATEMENT 2: REWARD POINTS PROGRAM AND INTEREST-FREE GRACE PERIOD",
                "text": (
                    "2.1 Reward Points Earnings: Cardholders earn 2 reward points per ₹100 spent on domestic dining and groceries. All other "
                    "retail transactions earn 1 reward point per ₹100. Fuel transactions, wallet loads, and cash withdrawals are excluded.\n\n"
                    "2.2 Interest-Free Grace Period: The credit card offers an interest-free grace period of up to 48 days from the transaction "
                    "date, provided the previous statement balance was settled in full by the payment due date.\n\n"
                    "2.3 Late Payment Fee Slabs: Late payment fees range from ₹100 for balances up to ₹1,000, up to ₹1,200 for outstanding "
                    "statement balances exceeding ₹50,000."
                )
            }
        ]
    }
]

def generate_and_index_documents():
    os.makedirs(DOCS_DIR, exist_ok=True)
    all_chunks_for_retriever = []

    with SessionLocal() as db:
        for doc_info in SAMPLE_DOCS:
            pdf_path = os.path.join(DOCS_DIR, doc_info["filename"])
            create_sample_pdf(pdf_path, doc_info["title"], doc_info["pages"])

            with open(pdf_path, "rb") as f:
                content_bytes = f.read()
            c_hash = compute_content_hash(content_bytes)

            # Check if document already stored (idempotency check FR-DOC-7)
            doc_rec = db.query(Document).filter_by(filename=doc_info["filename"]).first()
            if doc_rec:
                # Update content hash and delete old chunks to re-index fresh dense chunks
                doc_rec.content_hash = c_hash
                db.query(Chunk).filter_by(doc_id=doc_rec.doc_id).delete()
                db.flush()
            else:
                doc_rec = Document(
                    user_id=1,
                    filename=doc_info["filename"],
                    doc_type=doc_info["doc_type"],
                    content_hash=c_hash,
                    status="processed"
                )
                db.add(doc_rec)
                db.flush()

            # Extract and chunk
            extracted_pages = extract_text_from_pdf(pdf_path)
            chunks_data = chunk_document(extracted_pages, chunk_size_words=180, overlap_words=30)

            for cd in chunks_data:
                emb = get_text_embedding(cd["text"])
                chunk_obj = Chunk(
                    doc_id=doc_rec.doc_id,
                    page_number=cd["page_number"],
                    section_title=cd["section_title"],
                    text=cd["text"],
                    tsv=cd["text"],
                    embedding=emb,
                    chunk_hash=cd["chunk_hash"]
                )
                db.add(chunk_obj)
                all_chunks_for_retriever.append({
                    "chunk_id": chunk_obj.chunk_id,
                    "doc_id": doc_rec.doc_id,
                    "doc": doc_info["filename"],
                    "page": cd["page_number"],
                    "section": cd["section_title"],
                    "text": cd["text"],
                    "embedding": emb,
                    "user_id": 1
                })

            db.commit()

    print(f"Generated and indexed {len(SAMPLE_DOCS)} comprehensive documents with {len(all_chunks_for_retriever)} total dense chunks.")
    return all_chunks_for_retriever

if __name__ == "__main__":
    generate_and_index_documents()
