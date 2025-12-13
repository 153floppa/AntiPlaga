def calculate_sum(numbers):
    total =    0 #задаем переменную
    for num in numbers:
        total += num
    return total # это возврат значения

result = calculate_sum([1])
print(result)


