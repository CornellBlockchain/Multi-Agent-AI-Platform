# Introduction to Machine Learning

## Gradient Descent and Learning Rate
Gradient descent is an optimization method used to update model weights so that a loss function becomes smaller. At each iteration, the model computes a gradient of the loss with respect to the weights. The learning rate controls how large each update will be. An excessively large learning rate can overshoot a minimum; a very small learning rate may make training slow.

## Overfitting and Generalization
Overfitting happens when a model memorizes patterns and noise in its training data rather than learning relationships that generalize. A validation set helps estimate performance on unseen examples. Regularization and early stopping can reduce overfitting, but the best approach depends on the model and data.

## Train, Validation, and Test Splits
Training data is used to fit model parameters, validation data supports model selection, and a held-out test set estimates final performance. Reusing the test set repeatedly during tuning can bias the final evaluation.
