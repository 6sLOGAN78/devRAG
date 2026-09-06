package service

import (
	"encoding/json"
	"errors"
	"github.com/6sLOGAN78/devRAG/internal/dao"
)

type SaveCanvasReq struct {
	ID    string `json:"id" binding:"required"`
	Graph struct {
		Nodes []interface{} `json:"nodes"`
		Edges []interface{} `json:"edges"`
	} `json:"graph" binding:"required"`
}

type SaveCanvasResp struct {
	Success bool `json:"success"`
}

type GetCanvasResp struct {
	ID    string `json:"id"`
	Graph struct {
		Nodes []interface{} `json:"nodes"`
		Edges []interface{} `json:"edges"`
	} `json:"graph"`
}

func SaveCanvas(tenantID, userID string, req *SaveCanvasReq) error {
	// Re-serialize the graph for storage
	graphJSON, err := json.Marshal(req.Graph)
	if err != nil {
		return errors.New("invalid graph structure")
	}

	canvas := &dao.AgentCanvas{
		ID:              req.ID,
		TenantID:        tenantID,
		Name:            "Agent Workflow", // Default name, could be provided via req
		GraphDefinition: string(graphJSON),
		CreatedBy:       userID,
	}

	return dao.SaveAgentCanvas(canvas)
}

func GetCanvas(id, tenantID string) (*GetCanvasResp, error) {
	canvas, err := dao.GetAgentCanvasByIDAndTenant(id, tenantID)
	if err != nil {
		return nil, err
	}

	resp := &GetCanvasResp{
		ID: canvas.ID,
	}

	if err := json.Unmarshal([]byte(canvas.GraphDefinition), &resp.Graph); err != nil {
		return nil, errors.New("failed to parse graph definition")
	}

	return resp, nil
}
