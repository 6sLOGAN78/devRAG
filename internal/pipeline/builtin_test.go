package pipeline

import (
	"github.com/stretchr/testify/require"
	"testing"
)

func TestStaticCatalogIsFiniteAndReturnedCopiesAreIndependent(t *testing.T) {
	catalog := Builtins()
	require.Len(t, catalog, 14)
	ids := map[string]bool{}
	for _, v := range catalog {
		require.False(t, ids[v.ID])
		ids[v.ID] = true
		require.Equal(t, v.ID, v.ParserID)
		require.NotEmpty(t, v.Description)
		require.NotNil(t, v.ParserConfig)
		require.Equal(t, v.ID == "naive" || v.ID == "one" || v.ID == "manual" || v.ID == "qa" || v.ID == "book" || v.ID == "paper" || v.ID == "laws", v.Available)
	}
	catalog[0].ParserConfig["credential"] = "test-only-mutation"
	catalog[0].Name = "changed"
	again, _ := Builtin("naive")
	require.Equal(t, "General", again.Name)
	require.NotContains(t, again.ParserConfig, "credential")
	_, ok := Builtin("unknown")
	require.False(t, ok)
}
