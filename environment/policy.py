"""Normalize local models, XPolicyLab clients and explicitly mapped native policy APIs."""

from __future__ import annotations

from collections.abc import Callable


class PolicyAdapter:
    def reset(self):
        raise NotImplementedError

    def predict(self, observation):
        raise NotImplementedError

    def feedback(self, feedback):
        pass

    def finish(self, result):
        pass


class LocalModelPolicy(PolicyAdapter):
    def __init__(self, model):
        self.model = model

    def reset(self):
        self.model.reset()

    def predict(self, observation):
        from XPolicyLab.utils.process_data import decode_obs_images

        # Same shared decode boundary as PolicyServer, never decoding in model.py.
        self.model.update_obs(decode_obs_images(observation))
        return self.model.get_action()

    def feedback(self, feedback):
        hook = getattr(self.model, "on_execution_feedback", None)
        if callable(hook):
            hook(feedback.to_dict())

    def finish(self, result):
        hook = getattr(self.model, "on_trial_end", None)
        if callable(hook):
            hook(result.to_dict())


class ClientPolicy(PolicyAdapter):
    def __init__(self, client, *, step_feedback: bool = False, trial_feedback: bool = True):
        self.client = client
        # Per-step hooks are opt-in for compatibility with older policy servers.
        self.step_feedback = step_feedback
        self.trial_feedback = trial_feedback

    def reset(self):
        self.client.call(func_name="reset")

    def predict(self, observation):
        self.client.call(func_name="update_obs", obs=observation)
        return self.client.call(func_name="get_action")

    def feedback(self, feedback):
        if self.step_feedback:
            self.client.call(func_name="on_execution_feedback", obs=feedback.to_dict())

    def finish(self, result):
        if self.trial_feedback:
            self.client.call(func_name="trial_end", obs=result.to_dict())


class MappedPolicy(PolicyAdapter):
    """Bridge native APIs without guessing camera names, normalization, or action coordinates."""

    def __init__(self, *, reset: Callable, infer: Callable, observation_mapper: Callable,
                 action_mapper: Callable, feedback=None, finish=None):
        self.reset_fn = reset
        self.infer_fn = infer
        self.observation_mapper = observation_mapper
        self.action_mapper = action_mapper
        self.feedback_fn = feedback
        self.finish_fn = finish

    def reset(self):
        self.reset_fn()

    def predict(self, observation):
        return self.action_mapper(self.infer_fn(self.observation_mapper(observation)))

    def feedback(self, feedback):
        if self.feedback_fn is not None:
            self.feedback_fn(feedback.to_dict())

    def finish(self, result):
        if self.finish_fn is not None:
            self.finish_fn(result.to_dict())
