jQuery(function($){
// Initialize DataTables.js
$(document).ready(function() {
    $('#itemsTable').DataTable({responsive: true});
});

// Initialize JSON Editor
var editor = new JSONEditor(document.getElementById('jsonEditorContainer'), {
    mode: 'code',
    modes: ['code', 'form', 'text'],
    onChange: function() {
        var json = editor.get();
    }
});

// Show modal to create new item
$('#createBtn').click(function() {
    editor.set({});
    $('#modalTitle').text('Create Item');
    $('#modal').show();
    $('#saveBtn').off('click').on('click', function() {
        var json = editor.get();
        var requestData = {
            "item": JSON.stringify(json)  // Wrap your JSON object as a string inside the "item" key
        };

        $.ajax({
            url: '/item/create',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(requestData),  // Send as JSON in the request body
            success: function(response) {
                alert('Item created!');
                location.reload();
            },
            error: function(xhr, status, error) {
                alert('Error creating item: ' + xhr.responseText);
            }
        });
    });
});

// Show modal to update existing item
$('.updateBtn').click(function() {
    var itemId = $(this).data('id');
    $.get('/item/update/' + itemId, function(response) {
        editor.set(response);
        $('#modalTitle').text('Update Item');
        $('#modal').show();
        $('#saveBtn').off('click').on('click', function() {
            var json = editor.get(); // Retrieve the updated JSON from the editor
            var requestData = {
                "item": JSON.stringify(json) // Wrap the JSON object as a string under the "item" key
            };

            $.ajax({
                url: '/item/update/' + itemId, // Update URL endpoint with the specific item ID
                type: 'POST', // Use the PUT method for updates
                contentType: 'application/json', // Set content type to JSON
                data: JSON.stringify(requestData), // Send the data as a JSON string
                success: function(response) {
                    alert('Item updated!');
                    location.reload(); // Refresh the page after successful update
                },
                error: function(xhr, status, error) {
                    alert('Error updating item: ' + xhr.responseText);
                }
            });
        });
    }).fail(function() {
        alert('Error fetching item data');
    });
});

// Delete item
$('.deleteBtn').click(function() {
    var itemId = $(this).data('id');
    if (confirm('Are you sure you want to delete this item?')) {
        $.post('/item/delete/' + itemId, function() {
            alert('Item deleted!');
            location.reload();
        }).fail(function() {
            alert('Error deleting item');
        });
    }
});

// Close modal
$('#modalClose').click(function() {
    $('#modal').hide();
});

}); 