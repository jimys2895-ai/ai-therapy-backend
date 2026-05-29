from fastapi import APIRouter, HTTPException, Depends, status, Path, Query
from typing import List, Optional
from bson import ObjectId
from datetime import datetime
from pydantic import BaseModel, Field

from ....database import get_patients_collection
from ....models.patients import (
    Patient, PatientCreate, PatientResponse, PatientUpdate, DifficultyLevel
)
from ....auth.dependencies import get_current_user, require_admin
from ....models.users import User

router = APIRouter()

# Response models for OpenAPI documentation
class MessageResponse(BaseModel):
    message: str = Field(..., description="Response message", example="Operation completed successfully")

class PatientListResponse(BaseModel):
    patients: List[PatientResponse] = Field(..., description="List of patients")
    total_count: int = Field(..., description="Total number of patients", example=6)

class InitializePatientsResponse(BaseModel):
    message: str = Field(..., description="Initialization result message")
    patients_created: int = Field(..., description="Number of patients created", example=6)
    total_patients: int = Field(..., description="Total patients in database", example=6)
    patient_ids: Optional[List[str]] = Field(None, description="List of created patient IDs")

# Patient personas data from patientinfo.md
PATIENT_PERSONAS = [
    {
        "name": "Natalie Rosen",
        "age": 30,
        "pronouns": "She/Her",
        "occupation": "Freelance Graphic Designer",
        "condition": "Persistent Depressive Disorder (Dysthymia)",
        "personality": "Bubbly, outgoing personality, quick to laugh or self-deprecate. Beneath friendly demeanor, struggles with persistent inadequacy thoughts.",
        "background": "Struggles with intrusive thoughts related to body image, low self-worth, and negative self-talk",
        "difficulty": DifficultyLevel.INTERMEDIATE,
        "avatar": "👩‍💼",
        "symptoms": ["Low self-esteem", "Body image distortion", "Rumination", "Negative self-talk"],
        "emotional_state": "Friendly but internally struggling, self-deprecating",
        "presenting_problem": "Intrusive thoughts related to body image, low self-worth, and negative self-talk",
        "biological_profile": "No current medical conditions, occasional sleep disturbances and somatic symptoms during stress. Menstrual cycle fluctuations intensify emotional vulnerability.",
        "psychological_profile": "Diagnosed with Persistent Depressive Disorder with anxious features. Enduring patterns of low self-esteem, internalized negative core beliefs. History of suicidal ideation and one attempt at age 16.",
        "social_profile": "Lives alone, has close-knit friend group. Single and experiencing distress around romantic rejection. Freelance work provides flexibility but can exacerbate isolation.",
        "somatic_profile": "Body image distortion, tension in shoulders and jaw, teeth clenching during sleep. Feels 'pit in stomach' when experiencing shame.",
        "detailed_history": "History of suicidal ideation and one suicide attempt at age 16 via intentional overdose. Currently reports passive suicidal thoughts without active intent.",
        "strengths": ["Insightful and emotionally expressive", "Strong rapport-building skills", "Actively engaged in therapeutic work", "Supportive peer relationships", "Creative outlet through art and journaling"],
        "barriers": ["Deep-seated negative core beliefs", "Rumination and overgeneralization", "Fear of rejection", "Difficulty tolerating distress"],
        "learning_objectives": ["Practice identifying and challenging negative core beliefs", "Demonstrate validation and emotional attunement", "Apply CBT and self-compassion strategies", "Explore protective factors", "Engage in safety planning"],
        "dialogue_responses": [
            "Honestly? I just want to feel like I'm not broken. I laugh a lot, but inside I'm... a mess.",
            "That I'm ugly. That no one will ever want to be with me. That I'm always the friend and never the girlfriend.",
            "Usually after I scroll Instagram or if a date ghosts me. It's like this spiral: 'Of course he ghosted you. Who would want you?'",
            "Yeah, when I was 16, I took my mom's pills. It was impulsive. I didn't want to die, I just didn't want to feel so worthless.",
            "I draw a lot. And journal. Sometimes I text my best friend and she reminds me I'm not as awful as I think.",
            "To not hate myself every time I look in the mirror. To actually believe someone could love me.",
            "Thanks. I want to believe that. I really do."
        ]
    },
    {
        "name": "David Morales",
        "age": 54,
        "pronouns": "He/Him",
        "occupation": "Mail Carrier, United States Postal Service (32 years)",
        "condition": "PTSD with Alcohol Use Disorder",
        "personality": "Strong work ethic, uses humor and dry wit as coping mechanism. Initially resistant but shows insight when rapport is built.",
        "background": "U.S. Army Veteran – Infantry, served in Desert Storm and deployed for peacekeeping missions post-9/11. Recent tension at home.",
        "difficulty": DifficultyLevel.ADVANCED,
        "avatar": "👨‍💼",
        "symptoms": ["Nightmares", "Hypervigilance", "Irritability", "Emotional numbing", "Increased alcohol consumption"],
        "emotional_state": "On edge, defensive, uses humor as armor",
        "presenting_problem": "Recent tension at home, wife encouraged therapy after episode of shouting at daughter. Feeling 'on edge all the time', sleeping poorly, drinking more.",
        "biological_profile": "4-6 beers nightly, sometimes more on weekends. Never missed work in 30+ years but admits 'running on fumes'.",
        "psychological_profile": "PTSD from combat exposure and witnessing IED-related deaths. Alcohol Use Disorder (moderate to severe). Emotional numbing, difficulty experiencing joy.",
        "social_profile": "Married 26 years to Lisa, two children (Jake 22, Elena 17). Latino, Catholic (non-practicing). Strong work ethic and occupational stability.",
        "somatic_profile": "Sleep disturbances, hypervigilance, physical tension from trauma responses.",
        "detailed_history": "Combat veteran with witnessed trauma. Avoids talking about military service. Fear of being seen as 'weak' if he opens up.",
        "strengths": ["Strong work ethic", "Humor and dry wit", "Committed to family", "Verbalizes desire for change", "Insightful when rapport is built"],
        "barriers": ["Masculinity and stigma around therapy", "Fear of being judged", "Distrust in systems", "Shame and fear of losing control"],
        "learning_objectives": ["Build trust and rapport", "Address trauma-informed care", "Explore masculinity and therapy stigma", "Assess alcohol use patterns", "Safety planning for family"],
        "dialogue_responses": [
            "So, how does this work? You gonna fix me or what?",
            "Lisa says I scare her sometimes… I don't mean to. I just… snap.",
            "It's not like I'm drunk on the job or anything. It helps me sleep, that's all.",
            "That's not something I talk about. I don't even want to go there.",
            "You're alright. You don't push too hard. Maybe I could come back.",
            "If I didn't laugh, I'd probably lose it. Humor's my body armor."
        ]
    },
    {
        "name": "Jordan Williams",
        "age": 16,
        "pronouns": "He/Him",
        "occupation": "11th grade student",
        "condition": "Identity-related anxiety and depression",
        "personality": "Withdrawn, emotionally guarded, demonstrates occasional insight when trust is built. High emotional sensitivity.",
        "background": "School performance decline and withdrawn mood. Identifies as gay but hasn't disclosed to conservative, religious family.",
        "difficulty": DifficultyLevel.INTERMEDIATE,
        "avatar": "👨‍🎓",
        "symptoms": ["Low mood", "Social withdrawal", "Difficulty concentrating", "Reduced motivation", "Emotional numbing"],
        "emotional_state": "Anxious, fearful, emotionally fatigued from monitoring behavior",
        "presenting_problem": "School performance decline and withdrawn mood",
        "biological_profile": "Healthy 16-year-old, occasional insomnia and low appetite during stress. Previously active in soccer team but recently withdrawn.",
        "psychological_profile": "Significant distress related to sexual identity and anticipated family rejection. High anxiety, internal conflict, fear of abandonment. No suicidal ideation reported.",
        "social_profile": "Lives with both parents and two younger siblings. Parents hold strong religious beliefs. Previously strong academic record but grades dropped significantly.",
        "somatic_profile": "Chronic muscle tension in neck and shoulders, headaches and chest tightness when anxious. Feels 'numb' when overwhelmed.",
        "detailed_history": "Identifies as gay but hasn't disclosed to anyone in family. Fears being disowned or emotionally abandoned. No access to LGBTQ+-affirming spaces.",
        "strengths": ["Academically capable in STEM", "Insightful and observant", "Enjoys music and guitar", "Deep thinker", "Previously kind and team-oriented"],
        "barriers": ["Fear around disclosing identity", "Distrust in therapy process", "Social isolation", "Rigid family belief system", "Emotional numbing"],
        "learning_objectives": ["Build trust and safety", "Explore identity development", "Address family dynamics", "Develop coping strategies", "Connect to affirming resources"],
        "dialogue_responses": [
            "I don't know... this feels weird talking to someone I don't know.",
            "School's fine, I guess. Just harder to focus lately.",
            "My parents think something's wrong with me. Maybe they're right.",
            "I used to play soccer but... I don't know, I just don't feel like it anymore.",
            "Sometimes I feel like I'm pretending to be someone I'm not.",
            "What if my family doesn't accept who I really am?"
        ]
    },
    {
        "name": "Mark Reynolds",
        "age": 54,
        "pronouns": "He/Him",
        "occupation": "Elementary School Teacher (Literacy Specialist)",
        "condition": "Relationship difficulties with emotional processing challenges",
        "personality": "Intellectually strong, reflective, describes himself as 'emotionally stunted'. High verbal intelligence with emerging emotional insight.",
        "background": "Difficulty with emotional identification and self-described lack of empathy. Seeking growth and possible reconciliation after infidelity.",
        "difficulty": DifficultyLevel.ADVANCED,
        "avatar": "👨‍🏫",
        "symptoms": ["Emotional detachment", "Difficulty identifying emotions", "Relationship dysfunction", "Self-criticism"],
        "emotional_state": "Intellectually engaged but emotionally disconnected, motivated for change",
        "presenting_problem": "Difficulty with emotional identification and self-described lack of empathy; seeking growth and possible reconciliation in marriage after infidelity",
        "biological_profile": "No known chronic medical conditions. Good physical health, consistent energy levels. Increased tension during relational stress.",
        "psychological_profile": "History of infidelity and sexual behavior outside marriage. Strong cognitive functioning, recent progress in emotional labeling. No SI/HI or trauma history.",
        "social_profile": "Married 23 years, relationship strained after infidelity discovery. Two adult children with whom he shares close relationships. Small circle of friends through work.",
        "somatic_profile": "Physical sensations of emotion described as 'foreign' but improving. Uses mindfulness and breathwork to enhance body-emotion awareness.",
        "detailed_history": "Childhood described as emotionally muted, emotions not acknowledged. Consciously worked to break this cycle with his own children.",
        "strengths": ["High engagement with treatment", "Reflective and articulate", "Committed to children", "Consistent motivation for growth", "Passionate educator"],
        "barriers": ["Deep-rooted emotional avoidance", "Shame around relational failure", "Difficulty with authentic dialogue", "Self-perception as 'defective'", "Tendency to intellectualize"],
        "learning_objectives": ["Develop emotional vocabulary", "Practice emotional identification", "Explore attachment patterns", "Address shame and self-criticism", "Improve relational skills"],
        "dialogue_responses": [
            "I've been told I'm emotionally unavailable. I'm starting to think that might be true.",
            "I can analyze emotions intellectually, but feeling them? That's where I struggle.",
            "My wife says I'm like talking to a wall sometimes. I don't mean to be.",
            "I know I've hurt people, but I don't always understand how or why.",
            "With my students, emotions come naturally. With adults, especially my wife, it's different.",
            "I want to change, but I'm not sure I know how to feel things the way other people do."
        ]
    },
    {
        "name": "Sarah Mitchell",
        "age": 24,
        "pronouns": "She/Her",
        "occupation": "Graduate Student",
        "condition": "Relationship trauma and emotional manipulation recovery",
        "personality": "Highly intelligent, insightful, deeply reflective. Emotionally paralyzed by fear of loss and potential rather than reality.",
        "background": "Ambivalence and emotional distress regarding whether to remain in controlling, emotionally manipulative relationship.",
        "difficulty": DifficultyLevel.INTERMEDIATE,
        "avatar": "👩‍🎓",
        "symptoms": ["Emotional paralysis", "Anxiety", "Self-doubt", "Difficulty with decision-making"],
        "emotional_state": "Conflicted, emotionally exhausted, hopeful but fearful",
        "presenting_problem": "Ambivalence and emotional distress regarding whether to remain in a long-term romantic relationship characterized by control, emotional manipulation, and restriction of autonomy",
        "biological_profile": "Good physical health, sleep disrupted during emotional conflict. Appetite varies with mood, skips meals during intense episodes.",
        "psychological_profile": "No formal diagnoses, current symptoms consistent with anxiety and relational trauma. Highly intelligent with strong analytical skills. Emotional regulation difficulties.",
        "social_profile": "Support system limited due to partner's controlling behaviors. Previously close friendships strained. Longing for reconnection but hesitant without partner's approval.",
        "somatic_profile": "Suppresses emotions to maintain peace. Trouble identifying and prioritizing own needs. History of minimizing discomfort to accommodate others.",
        "detailed_history": "Partner exhibits emotional coercion, rigidity, controlling tendencies. His rules restrict her freedom inconsistently applied to himself. Demands high emotional labor.",
        "strengths": ["Highly intelligent and articulate", "Deeply reflective", "Strong ethical compass", "Motivated to change", "Capacity for positive reframing"],
        "barriers": ["Cognitive dissonance", "Fear of regret and loss", "Learned passivity", "Emotional suppression", "Idealization of relationship potential"],
        "learning_objectives": ["Explore relationship dynamics", "Identify manipulation patterns", "Develop assertiveness skills", "Process fear of loss", "Build support network"],
        "dialogue_responses": [
            "I know something's not right, but I keep thinking maybe it will get better.",
            "He says he loves me, but sometimes I feel like I'm walking on eggshells.",
            "I used to have so many friends. Now I barely see anyone.",
            "What if I leave and regret it? What if this is as good as it gets?",
            "I feel like I've lost myself somewhere along the way.",
            "I want to be happy, but I'm scared of making the wrong choice."
        ]
    },
    {
        "name": "Jenna Thompson",
        "age": 15,
        "pronouns": "She/Her",
        "occupation": "10th grade student",
        "condition": "Depression with ADHD and suicidal ideation",
        "personality": "Emotionally sensitive with strong creative instincts. Alternates between emotional shutdown and intense vulnerability. Often combative about therapy.",
        "background": "Suicidal ideation and mood instability related to bullying, self-esteem, and impulsivity.",
        "difficulty": DifficultyLevel.ADVANCED,
        "avatar": "👩‍🎓",
        "symptoms": ["Suicidal ideation", "Mood instability", "Impulsivity", "Low self-esteem", "Social withdrawal"],
        "emotional_state": "Depressed, hopeless, emotionally reactive",
        "presenting_problem": "Suicidal ideation and mood instability related to bullying, self-esteem, and impulsivity",
        "biological_profile": "Diagnosed with ADHD, combined presentation. No current medications. Reports difficulty with impulse control, racing thoughts, sleep irregularities.",
        "psychological_profile": "Depression symptoms including sadness, hopelessness, withdrawal. Recent increase in suicidal ideation. No specific plan but impulsivity is clinical concern.",
        "social_profile": "Lives with both parents and younger brother. Mother highly engaged, father dismissive of therapy. Few distant friends, increasingly isolated.",
        "somatic_profile": "Tension in chest and shoulders when anxious, restlessness, difficulty sleeping. Somatic complaints increase when discussing body image or bullying.",
        "detailed_history": "Bullying at school centers on appearance. Compares herself negatively to peers in dance classes. Previously enjoyed dance but now feels uncomfortable.",
        "strengths": ["High emotional sensitivity", "Strong creative instincts", "Previously passionate about dance", "Close relationship with mother", "Strong verbal communication when calm"],
        "barriers": ["Resistance to therapy", "Peer bullying and body image distress", "ADHD-related impulsivity", "Low self-esteem", "Suicidal ideation with impulsive tendencies"],
        "learning_objectives": ["Build therapeutic rapport", "Assess and manage suicide risk", "Address bullying and self-esteem", "Develop emotional regulation skills", "Engage family support"],
        "dialogue_responses": [
            "I don't want to be here. This is stupid.",
            "Everyone at school thinks I'm ugly and weird. Maybe they're right.",
            "Sometimes I just wish I could disappear and not have to deal with any of this.",
            "My dad says therapy is for crazy people. Am I crazy?",
            "I used to love dancing, but now I just feel fat and clumsy.",
            "Why should I even try? Nothing ever gets better."
        ]
    }
]


@router.post("/initialize", 
    response_model=InitializePatientsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize patient personas",
    description="Initialize all patient personas from clinical vignettes into the database",
    responses={
        201: {
            "description": "Patients initialized successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Successfully initialized 6 patient personas",
                        "patients_created": 6,
                        "total_patients": 6,
                        "patient_ids": ["507f1f77bcf86cd799439011", "507f1f77bcf86cd799439012"]
                    }
                }
            }
        },
        200: {
            "description": "Patients already exist",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Patients already initialized. Found 6 existing patients.",
                        "patients_created": 0,
                        "total_patients": 6,
                        "patient_ids": None
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        500: {"description": "Failed to initialize patients"}
    }
)
async def initialize_patients(current_user: User = Depends(get_current_user)):
    """
    Initialize all patient personas in the database.
    
    Creates 6 comprehensive patient personas based on clinical vignettes:
    - **Natalie Rosen** (30, Depression) - Intermediate difficulty
    - **David Morales** (54, PTSD/Alcohol) - Advanced difficulty  
    - **Jordan Williams** (16, Identity/Anxiety) - Intermediate difficulty
    - **Mark Reynolds** (54, Relationship/Emotional) - Advanced difficulty
    - **Sarah Mitchell** (24, Relationship Trauma) - Intermediate difficulty
    - **Jenna Thompson** (15, Depression/ADHD/Suicidal) - Advanced difficulty
    
    Each persona includes complete clinical profiles, dialogue responses, and learning objectives.
    """
    try:
        patients_collection = get_patients_collection()
        
        # Check if patients already exist
        existing_count = await patients_collection.count_documents({})
        if existing_count > 0:
            return {
                "message": f"Patients already initialized. Found {existing_count} existing patients.",
                "patients_created": 0,
                "total_patients": existing_count
            }
        
        # Create patient documents
        created_patients = []
        for persona_data in PATIENT_PERSONAS:
            patient_doc = {
                "_id": str(ObjectId()),
                **persona_data,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "is_active": True
            }
            created_patients.append(patient_doc)
        
        # Insert all patients
        result = await patients_collection.insert_many(created_patients)
        
        return {
            "message": f"Successfully initialized {len(result.inserted_ids)} patient personas",
            "patients_created": len(result.inserted_ids),
            "total_patients": len(result.inserted_ids),
            "patient_ids": [str(id) for id in result.inserted_ids]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize patients: {str(e)}"
        )


@router.get("/",
    response_model=PatientListResponse,
    summary="Get all patients",
    description="Retrieve list of all patient personas with optional filtering by difficulty level",
    responses={
        200: {
            "description": "Patients retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "patients": [
                            {
                                "id": "507f1f77bcf86cd799439011",
                                "name": "Natalie Rosen",
                                "age": 30,
                                "condition": "Persistent Depressive Disorder (Dysthymia)",
                                "difficulty": "intermediate",
                                "avatar": "👩‍💼",
                                "symptoms": ["Low self-esteem", "Body image distortion"],
                                "emotional_state": "Friendly but internally struggling"
                            }
                        ],
                        "total_count": 6
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        500: {"description": "Failed to retrieve patients"}
    }
)
async def get_all_patients(
    difficulty: Optional[DifficultyLevel] = Query(None, description="Filter by difficulty level"),
    is_active: bool = Query(True, description="Filter by active status"),
    current_user: User = Depends(get_current_user)
):
    """
    Get all patient personas with optional filtering.
    
    - **difficulty**: Filter by difficulty level (beginner, intermediate, advanced)
    - **is_active**: Filter by active status (default: true)
    
    Returns a list of patient personas available for therapy training sessions.
    Each patient includes comprehensive clinical information and dialogue responses.
    """
    try:
        patients_collection = get_patients_collection()
        
        # Build filter query
        filter_query = {"is_active": is_active}
        if difficulty:
            filter_query["difficulty"] = difficulty
        
        # Get patients from database
        cursor = patients_collection.find(filter_query)
        patients = await cursor.to_list(length=None)
        
        if not patients:
            return []
        
        # Convert to response models with proper ID mapping
        patient_responses = []
        for patient in patients:
            # Map _id to id for frontend compatibility
            patient_dict = dict(patient)
            patient_dict["id"] = patient_dict.get("_id")
            print(f"Patient mapping: _id={patient_dict.get('_id')} -> id={patient_dict.get('id')}")
            patient_responses.append(PatientResponse(**patient_dict))
        
        return PatientListResponse(
            patients=patient_responses,
            total_count=len(patient_responses)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve patients: {str(e)}"
        )


@router.get("/{patient_id}",
    response_model=PatientResponse,
    summary="Get patient by ID",
    description="Retrieve detailed information about a specific patient persona",
    responses={
        200: {
            "description": "Patient retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "507f1f77bcf86cd799439011",
                        "name": "Natalie Rosen",
                        "age": 30,
                        "condition": "Persistent Depressive Disorder (Dysthymia)",
                        "personality": "Bubbly, outgoing personality, quick to laugh or self-deprecate",
                        "difficulty": "intermediate",
                        "avatar": "👩‍💼",
                        "symptoms": ["Low self-esteem", "Body image distortion", "Rumination"],
                        "emotional_state": "Friendly but internally struggling",
                        "dialogue_responses": ["Honestly? I just want to feel like I'm not broken..."]
                    }
                }
            }
        },
        404: {"description": "Patient not found"},
        401: {"description": "Authentication required"},
        500: {"description": "Failed to retrieve patient"}
    }
)
async def get_patient(
    patient_id: str = Path(..., description="Patient ID to retrieve", example="507f1f77bcf86cd799439011"),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed information about a specific patient persona.
    
    Returns comprehensive clinical information including:
    - Complete biopsychosocial profile
    - Dialogue responses for AI simulation
    - Learning objectives for training
    - Strengths and barriers for therapeutic work
    """
    try:
        patients_collection = get_patients_collection()
        
        patient = await patients_collection.find_one({"_id": patient_id})
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found"
            )
        
        # Map _id to id for frontend compatibility
        patient_dict = dict(patient)
        patient_dict["id"] = patient_dict["_id"]
        
        return PatientResponse(**patient_dict)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve patient: {str(e)}"
        )


@router.post("/", response_model=PatientResponse)
async def create_patient(
    patient_data: PatientCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new patient (admin only)"""
    try:
        # Check if user is admin
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can create patients"
            )
        
        patients_collection = get_patients_collection()
        
        # Create patient document
        patient_doc = {
            "_id": str(ObjectId()),
            **patient_data.dict(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True
        }
        
        # Insert patient
        await patients_collection.insert_one(patient_doc)
        
        return PatientResponse(**patient_doc)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create patient: {str(e)}"
        )


@router.put("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: str,
    patient_update: PatientUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a patient (admin only)"""
    try:
        # Check if user is admin
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can update patients"
            )
        
        patients_collection = get_patients_collection()
        
        # Check if patient exists
        existing_patient = await patients_collection.find_one({"_id": patient_id})
        if not existing_patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found"
            )
        
        # Prepare update data
        update_data = {k: v for k, v in patient_update.dict().items() if v is not None}
        update_data["updated_at"] = datetime.utcnow()
        
        # Update patient
        await patients_collection.update_one(
            {"_id": patient_id},
            {"$set": update_data}
        )
        
        # Get updated patient
        updated_patient = await patients_collection.find_one({"_id": patient_id})
        return PatientResponse(**updated_patient)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update patient: {str(e)}"
        )


@router.delete("/{patient_id}")
async def delete_patient(
    patient_id: str,
    current_user: User = Depends(get_current_user)
):
    """Soft delete a patient (admin only)"""
    try:
        # Check if user is admin
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can delete patients"
            )
        
        patients_collection = get_patients_collection()
        
        # Check if patient exists
        existing_patient = await patients_collection.find_one({"_id": patient_id})
        if not existing_patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found"
            )
        
        # Soft delete (set is_active to False)
        await patients_collection.update_one(
            {"_id": patient_id},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
        )
        
        return {"message": "Patient deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete patient: {str(e)}"
        )