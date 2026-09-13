from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.deps import get_current_user, get_db
from app.models.agent import Agent
from app.models.user import User
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=AgentRead)
def create_agent(
    payload: AgentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent = Agent(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        system_prompt=payload.system_prompt,
        model=payload.model,
        temperature=payload.temperature,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("", response_model=list[AgentRead])
def list_agents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agents = db.exec(select(Agent).where(Agent.user_id == current_user.id)).all()
    return agents


@router.get("/{agent_id}", response_model=AgentRead)
def get_agent(
    agent_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    agent = db.get(Agent, agent_id)
    if not agent or agent.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentRead)
def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent = db.get(Agent, agent_id)
    if not agent or agent.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    data = payload.dict(exclude_unset=True)
    for key, value in data.items():
        setattr(agent, key, value)

    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=204)
def delete_agent(
    agent_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    agent = db.get(Agent, agent_id)
    if not agent or agent.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
