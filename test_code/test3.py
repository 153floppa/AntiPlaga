def calculate_sum(numbers):
    total = 0
    for num in numbers:
        total += num
    return total

def arr_sum(arr):
    s =0
    for i in arr:
        s = calculate_sum([s,i])
    return s

result = arr_sum([1])
print(result)