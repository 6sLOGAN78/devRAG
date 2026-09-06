import { visit } from 'unist-util-visit';

export default function remarkCitations() {
  return (tree: any) => {
    visit(tree, 'text', (node: any, index, parent) => {
      if (parent && (parent.type === 'code' || parent.type === 'inlineCode' || parent.type === 'link')) {
        return;
      }
      
      const value = node.value;
      const regex = /\[(\d+)\]/g;
      
      const matches = [...value.matchAll(regex)];
      if (matches.length === 0) return;
      
      const newNodes = [];
      let lastIndex = 0;
      
      for (const match of matches) {
        if (match.index > lastIndex) {
          newNodes.push({ type: 'text', value: value.slice(lastIndex, match.index) });
        }
        
        newNodes.push({
          type: 'citation',
          data: {
            hName: 'citation',
            hProperties: {
              citationindex: match[1]
            }
          }
        });
        
        lastIndex = match.index + match[0].length;
      }
      
      if (lastIndex < value.length) {
        newNodes.push({ type: 'text', value: value.slice(lastIndex) });
      }
      
      if (parent && index !== undefined && newNodes.length > 0) {
        parent.children.splice(index, 1, ...newNodes);
      }
    });
  };
}
