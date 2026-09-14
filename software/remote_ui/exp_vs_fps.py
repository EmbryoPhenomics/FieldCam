import matplotlib.pyplot as plt

e = list(range(1, 50, 5))
f = [106, 119, 136, 157, 188, 233, 293, 294, 294, 293]
f = f[::-1]
f = [i/10 for i in f]

plt.plot(e, f)
plt.show()