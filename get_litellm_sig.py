import litellm
import inspect

print(inspect.signature(litellm.RateLimitError.__init__))
